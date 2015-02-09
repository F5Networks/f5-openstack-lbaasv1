""" OpenStack LBaaS v1 iApp for BIG-IP """
# Copyright 2014 F5 Networks Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

PRESENTATION = r"""section intro {
    message blank " "
}

section vip {
    string addr        display "large" validator "IpAddress" required
    string port        display "large" validator "PortNumber" default "80"
    choice protocol    display "medium" default "http"
        { "http", "tcp" }
    choice persist     display "medium" default "http-cookie"
        { "source-ip", "http-cookie", "app-cookie", "none" }
    optional ( persist == "app-cookie" ) {
        string cookie  display "medium" default "jsessionid"
    }
    choice state       display "medium" default "enabled"
        { "enabled", "disabled" }
}

section pool {
    table members {
        string addr    display "large" validator "IpAddress"
        string port    display "small" validator "PortNumber" default "80"
        string connection_limit display "small" validator "NonNegativeNumber" default "10000"
        choice state   display "medium" default "enabled"
            { "enabled", "drain-disabled", "force-disabled" }
    }
    choice lb_method   display "xlarge" default "round-robin"
        { "round-robin", "least-connections-member" }
    choice monitor     display "xlarge" default "http"
        { "http", "tcp", "ping" }
}

text {
    intro "Load Balancer As A Service Template for BIG-IQ"
    intro.blank " "

    vip "Virtual Server"
    vip.addr "What is the virtual IP address?"
    vip.port "What is the virtual port number? (default: 80)"
    vip.protocol "What protocol optimization should be used on this VIP?"
    vip.persist "What persistence type should be used on this VIP?"
    vip.cookie "What application cookie should BIG-IP persist on?"
    vip.state "What is the VIP state?"

    pool "Pool"
    pool.members "Enter an address and TCP port number for each pool member. (default: 80)"
    pool.members.addr "IP"
    pool.members.port "Port"
    pool.members.connection_limit "Connection Limit"
    pool.members.state "State"
    pool.lb_method "What load balancing method should be used?"
    pool.monitor "What type of monitor should be used to determine pool health?"
}
"""

IMPLEMENTATION = r"""# Load Balancer As A Service iApp Template for BIG-IQ
#
# This simple load-balancing application template uses OpenStack
# terminology to create a BIG-IP configuration.
#
# In order to avoid present and future versioning issues, this
# template has no dependence on cli scripts or Tcl packages.
#
# Furthermore, for compatibility with BIG-IQ, no presentation
# logic is used and all APL variables are insured with default
# values as defined in the arrays shown below, called var_defaults
# and pool_defaults. Thus, the template will not abort merely
# because BIG-IQ fails to supply a given value. However, iApp
# implementation will still fail if BIG-IP rejects the resultant
# configuration. For example, the iApp will fail if HTTP_COOKIE
# persistence is chosen with TCP protocol optimization, since BIG-IP
# requires HTTP protocol optimization in order to offer cookie
# persistence.

array set var_defaults {
    vip__state enabled
    vip__addr Error
    vip__port 80
    vip__protocol http
    vip__persist http-cookie
    vip__cookie jsessionid
    pool__lb_method round-robin
    pool__monitor http
}

array set pool_defaults {
    pool__members {
        state enabled
        addr Error
        port 80
        connection_limit 1000
    }
}

# iRule from SOL7392: Overview of universal persistence
set persist_irule {
when HTTP_RESPONSE {
  if { \[HTTP::cookie exists \"$::vip__cookie\"\] } {
    persist add uie \[HTTP::cookie \"$::vip__cookie\"\]
  }
}
when HTTP_REQUEST {
  if { \[HTTP::cookie exists \"$::vip__cookie\"\] } {
    persist uie \[HTTP::cookie \"$::vip__cookie\"\]
  }
}}

array set pool_state {
    enabled        {session user-enabled  state user-up}
    disabled       {session user-disabled state user-up}
    drain-disabled {session user-disabled state user-up}
    force-disabled {state user-down}
}

array set monitor {
    ping {[tmsh_create ltm monitor gateway-icmp ${tmsh::app_name}_ping]}
    tcp  {[tmsh_create ltm monitor tcp ${tmsh::app_name}_tcp]}
    http {[tmsh_create ltm monitor http ${tmsh::app_name}_http]}
}

array set persist {
    none        {none}
    source-ip   {replace-all-with \{[tmsh_create ltm persistence \
                 source-addr ${tmsh::app_name}_source_ip]\}}
    http-cookie {replace-all-with \{[tmsh_create ltm persistence \
                 cookie ${tmsh::app_name}_http_cookie]\}}
    app-cookie  {replace-all-with \{[tmsh_create ltm persistence \
                 universal ${tmsh::app_name}_app_cookie \
                 rule [tmsh_create ltm rule ${tmsh::app_name}_cookie \
                 [subst $persist_irule]]]\}}
}

array set profiles {
    tcp  {none}
    http {replace-all-with \{[tmsh_create \
          ltm profile http ${tmsh::app_name}_http]\}}
}

# tmsh command wrapper that writes to scriptd log and returns object name
proc tmsh_create { args } {
    set args [join $args]
    puts "tmsh create $args"
    tmsh::create $args
    return [lindex $args [lsearch -glob $args "*_*"]]
}

# constructor that handles IPv6 and port number wildcards
proc destination { addr port } {

    # 0 and * represent wildcard port assignments in the GUI,
    # but TMSH requires the string 'any' to specify a wildcard
    if { $port eq "0" || $port eq "*" } {
        set port "any"
    }

    # decide on IPv4 or IPv6 delimiter
    set delimiter [expr {[string match "*:*:*" $addr] ? ".":":"}]
    return $addr$delimiter$port
}

# safely set any variables that do not exist
foreach var [array names var_defaults] {
    if { ![info exists ::$var] || [set ::$var] eq "" } {
        set ::$var $var_defaults($var)
    }
}

# safely set column values that do not exist
foreach table [array names pool_defaults] {
    if { ![info exists ::$table] } {
        set members none
    } else {
        array set column_defaults $pool_defaults($table)
        foreach row [set ::$table] {
            set params {}
            array unset column

            # extract the iApp table data
            foreach column_data [lrange [split [join $row] "\n"] 1 end-1] {
                set name [lindex $column_data 0]
                set column($name) [lindex $column_data 1]
            }

            # fill in any empty table values
            foreach name [array names column_defaults] {
                if { ![info exists column($name)] || $column($name) eq "" } {
                    set column($name) $column_defaults($name)
                }
                if { $name eq "state" } {
                    append params " $pool_state($column($name))"
                } elseif { $name ne "addr" && $name ne "port" } {
                    append params " [string map {_ -} $name] $column($name)"
                }
            }
            append members \
                " [destination $column(addr) $column(port)] \\\{$params\\\}"
        }
    }
}

# build the application
tmsh_create ltm virtual ${tmsh::app_name}_vip \
    $::vip__state ip-protocol tcp snat automap \
    destination [destination $::vip__addr $::vip__port] \
    pool [tmsh_create ltm pool ${tmsh::app_name}_pool \
    members replace-all-with \{ [join $members] \} \
    load-balancing-mode $::pool__lb_method \
    monitor  [subst $monitor($::pool__monitor)]] \
    persist  [subst $persist($::vip__persist)] \
    profiles [subst $profiles($::vip__protocol)]
"""


IAPP = {
    "name": "f5.lbaas",
    "actions": {
        "definition": {
            "implementation": IMPLEMENTATION,
            "presentation": PRESENTATION
        }
    }
}


def check_install_iapp(bigip):
    """ Ensure the iApp is installed if we should """
    if not bigip.iapp.template_exists('f5.lbaas', 'Common'):
        bigip.iapp.create_template('f5.lbaas', 'Common', IAPP)
