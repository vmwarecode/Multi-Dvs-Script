
import time
import re
from Utils.utils import Utils
import subprocess
import sys
import getpass

class NSXTAutomator:
    def __init__(self, args):
        self.utils = Utils(args)
        self.description = "NSX-T instance deployment"
        self.hostname = args[0]

    #If current handling domain is management domain, is_primary must be False
    def main_func(self, selected_domain_id, is_primary = True):
        three_line_separator = ['', '', '']
        nsxt_instances = self.__get_nsxt_instances(selected_domain_id, is_primary)
        if is_primary:
            if len(nsxt_instances) > 0:
                self.utils.printCyan("Please choose NSX-T instance option:")
                self.utils.printBold("1) Create new NSX-T instance (default)")
                self.utils.printBold("2) Use existing NSX-T instance")
                theoption = self.utils.valid_input("\033[1m Enter your choice(number): \033[0m", "1", self.__valid_option, ["1", "2"])
            else:
                self.utils.printYellow("** No shared NSX-T instance was found, you need to create a new one")
                theoption = "1"
        else:
            if len(nsxt_instances) == 0:
                #In a common situation, this is not possible
                self.utils.printRed("No shared NSX-T instance discovered in current domain")
                input("Enter to exit ...")
                sys.exit(1)
            else:
                theoption = "2"

        print(*three_line_separator, sep='\n')

        if theoption == "1":
            return self.option1_new_nsxt_instance()

        return self.option2_existing_nsxt(nsxt_instances)

    """
        In case of secondary cluster, the NSX-T cluster has to be the same as that of the primary cluster. 
        We don’t need to provide an option to create a new NSX-T cluster or list the NSX-T clusters that are not mapped to the primary cluster. 
        We can identify the NSX-T cluster based on the domain ID (as provided below).
        
        In case of primary cluster, the NSX-T cluster could be a new cluster or an existing one. 
        List only the NSX-T clusters that have the property isShareable as TRUE. 
        The management NSX-T cluster is dedicated to management domain and will have the isShareable property set to FALSE.
    """
    def __get_nsxt_instances(self, selected_domain_id, is_primary = True):
        self.utils.printGreen("Getting shared NSX-T cluster information...")
        url = 'https://'+self.hostname+'/v1/nsxt-clusters'
        response = self.utils.get_request(url)
        nsxinstances = []
        for oneins in response["elements"]:
            if is_primary and oneins["isShareable"]:
                nsxinstances.append(oneins)
            elif not is_primary:
                domainids = [onedomain["id"] for onedomain in oneins["domains"]]
                if selected_domain_id in domainids:
                    nsxinstances.append(oneins)
        return nsxinstances

    def option2_existing_nsxt(self, nsxt_instances):
        three_line_separator = ['', '', '']
        geneve_vlan = self.utils.valid_input("\033[1m Enter Geneve vLAN ID (0-4096): \033[0m ", None, self.__valid_vlan)
        print(*three_line_separator, sep='\n')

        self.utils.printCyan("Please select one NSX-T instance")
        ct = 0
        nsxt_map = {}
        for nsxt_inst in nsxt_instances:
            idx = str(ct + 1)
            ct += 1
            nsxt_map[idx] = nsxt_inst
            self.utils.printBold("{0}) NSX-T vip: {1}".format(idx, nsxt_inst["vipFqdn"]))

        choiceidx = self.utils.valid_input("\033[1m Enter your choice(number): \033[0m", None, self.__valid_option, nsxt_map.keys())
        selected_ins =nsxt_map[choiceidx]

        print(*three_line_separator, sep='\n')

        nsxTSpec = {
            "nsxManagerSpecs" :[
            ],
            "vip" : selected_ins["vip"],
            "vipFqdn": selected_ins["vipFqdn"]
        }
        for nsxnode in selected_ins["nodes"]:
            nsxTSpec["nsxManagerSpecs"].append(
                {
                    "name":nsxnode["name"],
                    "networkDetailsSpec":{
                        "dnsName":nsxnode["fqdn"],
                        "ipAddress": nsxnode["ipAddress"]
                    }
                }
            )

        return {"nsxTSpec":nsxTSpec, "geneve_vlan": geneve_vlan}


    def option1_new_nsxt_instance(self):
        three_line_separator = ['', '', '']
        geneve_vlan = self.utils.valid_input("\033[1m Enter Geneve vLAN ID (0-4096): \033[0m", None, self.__valid_vlan)
        admin_password = self.__handle_password_input()
        print(*three_line_separator, sep='\n')

        self.utils.printCyan("Please Enter NSX-T VIP details")
        nsxt_vip_fqdn = self.utils.valid_input("\033[1m FQDN (IP address will be fetched from DNS): \033[0m", None, self.__valid_fqdn)
        nsxt_gateway = self.utils.valid_input("\033[1m Gateway IP address: \033[0m", None, self.__valid_ip)
        nsxt_netmask = self.utils.valid_input("\033[1m Subnet mask (255.255.255.0): \033[0m", "255.255.255.0", self.__valid_ip)
        print(*three_line_separator, sep='\n')

        nsxt_1_fqdn = self.utils.valid_input("\033[1m Enter FQDN for 1st NSX-T Manager: \033[0m",
                                             None, self.__valid_fqdn)
        print(*three_line_separator, sep='\n')

        nsxt_2_fqdn = self.utils.valid_input("\033[1m Enter FQDN for 2nd NSX-T Manager: \033[0m",
                                             None, self.__valid_fqdn)
        print(*three_line_separator, sep='\n')

        nsxt_3_fqdn = self.utils.valid_input("\033[1m Enter FQDN for 3rd NSX-T Manager: \033[0m",
                                             None, self.__valid_fqdn)
        print(*three_line_separator, sep='\n')

        nsxTSpec = {
            "nsxManagerSpecs" :[
                self.__to_nsx_manager_obj( nsxt_1_fqdn, nsxt_gateway, nsxt_netmask),
                self.__to_nsx_manager_obj( nsxt_2_fqdn, nsxt_gateway, nsxt_netmask),
                self.__to_nsx_manager_obj( nsxt_3_fqdn, nsxt_gateway, nsxt_netmask)
            ],
            "vip" : self.__nslookup_ip_from_dns(nsxt_vip_fqdn),
            "vipFqdn": nsxt_vip_fqdn,
            "nsxManagerAdminPassword" : admin_password
        }

        return {"nsxTSpec":nsxTSpec, "geneve_vlan": geneve_vlan}

    def __to_nsx_manager_obj(self, fqdn, gateway, netmask):
        ip = self.__nslookup_ip_from_dns(fqdn)
        return {
            "name": fqdn.split('.')[0],
            "networkDetailsSpec": {
                "ipAddress" : ip,
                "dnsName": fqdn,
                "gateway": gateway,
                "subnetMask": netmask
            }
        }

    def __valid_option(self, inputstr, choices):
        choice = str(inputstr).strip().lower()
        if choice in choices:
            return choice
        self.utils.printYellow("**Use first choice by default")
        return list(choices)[0]

    def __valid_password(self, inputstr):
        return self.utils.password_check(inputstr)

    def __valid_vlan(self, inputstr):
        res = True
        if not str(inputstr).isdigit():
            res = False
        res = (int(inputstr) >=0 and int(inputstr) <= 4096)
        if not res:
            self.utils.printRed  ("VLAN must be a number in between 0-4096")
        return res

    def __valid_fqdn(self, inputstr):
        res = True
        if len(inputstr) <= 3 or len(inputstr) > 255:
            res = False
        elif "." not in inputstr:
            res = False
        elif inputstr[0] == "." or inputstr[-1] == ".":
            res = False
        else:
            segmatch = re.compile("[0-9 a-z A-Z _ -]")
            res = all((len(segmatch.sub('', oneseg)) == 0 and len(oneseg) > 0) for oneseg in inputstr.split("."))
        if not res:
            self.utils.printRed ("FQDN format is not correct")
        else:
            self.utils.printGreen("Resolving IP from DNS...")
            theip = self.__nslookup_ip_from_dns(inputstr)
            if theip is not None:
                self.utils.printGreen("Resolved IP address: {}".format(theip))
            else:
                res = False
                self.utils.printRed ("Hasn't found matched IP from DNS")

        return res

    def __valid_ip(self, inputstr):
        res = re.compile("(\d+\.\d+\.\d+\.\d+)").match(inputstr) is not None and all((int(seg) >=0 and int(seg)<=255) for seg in inputstr.split("."))
        if not res:
            self.utils.printRed("IP format is not correct")
        return res

    def __nslookup_ip_from_dns(self, fqdn):
        cmd = "nslookup {}".format(fqdn)
        sub_popen = subprocess.Popen(cmd,
                                     shell=True,
                                     stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE)
        output, err = sub_popen.communicate()
        if sub_popen.returncode >0:
            return None

        thenext = False
        # byte feature only supported in python 3
        for aline in output.decode('utf8').split("\n"):
            if thenext and str(aline).lower().startswith("address:"):
                return aline.split(":")[-1].strip()
            if str(aline).lower().startswith("name:"):
                tail = aline.split(":")[-1].strip()
                if tail == fqdn:
                    thenext = True
        return None

    def __handle_password_input(self):
        while(True):
            thepwd = getpass.getpass("\033[1m Enter Admin password: \033[0m")
            confirmpwd = getpass.getpass("\033[1m Confirm Admin password: \033[0m")
            if thepwd != confirmpwd:
                self.utils.printRed("Passwords don't match")
            else:
                return thepwd