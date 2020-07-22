__author__ = 'jradhakrishna'

import sys
import os
import time
import json
import copy
import getpass
import collections.abc
from Utils.utils import Utils
from domains.domainsautomator import DomainsAutomator
from clusters.clustersautomator import ClustersAutomator
from nsxt.nsxtautomator import NSXTAutomator
from vxrailManager.vxrailauthautomator import VxRailAuthAutomator
from license.licenseautomator import LicenseAutomator
from hosts.hostsautomator import HostsAutomator

MASKED_KEYS = ['password', 'nsxManagerAdminPassword']
UNMANAGED_CLUSTERS_CRITERION = 'UNMANAGED_CLUSTERS_IN_VCENTER'
UNMANAGED_CLUSTER_CRITERION = 'UNMANAGED_CLUSTER_IN_VCENTER'
MATCHING_VMNIC_CRITERION = 'UNMANAGED_CLUSTER_IN_VCENTER_MATCHING_PNICS_ACROSS_HOSTS'

class VxRaiWorkloadAutomator:
    def __init__(self):

        args = []
        args.append("localhost")
        args.append(input("\033[1m Enter the SSO username: \033[0m"))
        args.append(getpass.getpass("\033[1m Enter the SSO password: \033[0m"))
        self.utils = Utils(args)
        self.utils.printGreen('Welcome to VxRail Workload Automator')
        self.domains = DomainsAutomator(args)
        self.hosts = HostsAutomator(args)
        self.clusters = ClustersAutomator(args)
        self.nsxt = NSXTAutomator(args)
        self.vxrailmanager = VxRailAuthAutomator(args)
        self.licenses = LicenseAutomator(args)
        self.hostname = args[0]

    def let_user_pick(self, domain_selection_text, options):
        self.utils.printCyan(domain_selection_text)
        for idx, element in enumerate(options):
            self.utils.printBold("{}) {}".format(idx + 1, element['name']))
        while (True):
            inputstr = input("\033[1m Enter your choice(number): \033[0m")
            try:
                if 0 < int(str(inputstr).strip()) <= len(options):
                    return int(inputstr) - 1
                else:
                    inputstr = input(
                        "\033[1m Wrong input, Please input an option between 1(included) and {0}(included): \033[0m".format(
                            str(len(options))))
                    if 0 < int(str(inputstr).strip()) <= len(options):
                        return int(inputstr) - 1
            except:
                print("\033[1m Input a number between 1(included) and {0}(included)\033[0m".format(str(len(options))))

    def populatenetworkSpec(self, isExistingDvs=True, existingDvs=None, new_Dvs=None, nsxSpec=None, isPrimary=True):
        tempDvsSpec = {}
        tempDvsSpec['vdsSpecs'] = []
        if isExistingDvs:
            tempDvsSpec['vdsSpecs'].append(existingDvs)
        elif isPrimary and not isExistingDvs:
            tempDvsSpec['vdsSpecs'].append(new_Dvs)
        elif not isPrimary and not isExistingDvs:
            tempDvsSpec['vdsSpecs'].append(existingDvs)
            tempDvsSpec['vdsSpecs'].append(new_Dvs)

        tempDvsSpec['nsxClusterSpec'] = {
            "nsxTClusterSpec": {
                "geneveVlanId": int(nsxSpec["geneve_vlan"])
            }
        }
        return tempDvsSpec

    def populatehostSpec(self, isExistingDvs = True, hostsSpec = None, vmNics = None, uname = 'root', password = None):
        temp_hosts_spec = []
        for element in hostsSpec:
            hostSpec = {}
            hostSpec['ipAddress'] = element['ipAddress']
            hostSpec['hostName'] = element['hostName']
            hostSpec['username'] = uname
            hostSpec['password'] = password
            if not isExistingDvs:
                hostSpec['hostNetworkSpec']= {
                    "vmNics": vmNics
                }
            temp_hosts_spec.append(hostSpec)
        return temp_hosts_spec

    def populatensxtSpec(self, nsxt_payload = None, licenses_payload = None):
        nsxtSpec = nsxt_payload["nsxTSpec"]
        nsxtSpec["licenseKey"] = licenses_payload['licenseKeys']['NSX-T']
        return nsxtSpec

    def maskPasswords(self, obj):
        for k, v in obj.items():
            if isinstance(v, collections.abc.Mapping):
                obj[k] = self.maskPasswords(v)
            elif isinstance(v, list):
                for elem in v:
                    self.maskPasswords(elem)
            elif k in MASKED_KEYS:
                obj[k] = '*******'
            else:
                obj[k] = v
        return obj

    def getSystemDvs(self, dvsSpecs):
        if len(dvsSpecs) > 0 :
            for dvs in dvsSpecs:
                if "portGroupSpecs" in dvs and len(dvs["portGroupSpecs"]) > 0:
                    hasManagement = False
                    hasVsan = False
                    hasVmotion = False
                    for pg in dvs["portGroupSpecs"]:
                        if "transportType" in pg:
                            if pg["transportType"] == "MANAGEMENT":
                                hasManagement = True
                            elif pg["transportType"] == "VSAN":
                                hasVsan = True
                            elif pg["transportType"] == "VMOTION":
                                hasVmotion = True
                    if hasManagement and hasVsan and hasVmotion:
                        return dvs
        return None


    @property
    def initApp(self):
        #Get domains
        domains = self.domains.get_domains()
        domains_user_selection = list(map(lambda x: {"name": x['name'], "id": x['id']}, domains["elements"]))
        three_line_separator = ['', '', '']
        print(*three_line_separator, sep='\n')
        domain_selection_text = "Please choose the domain to which cluster has to be imported:"
        domain_index = self.let_user_pick(domain_selection_text, domains_user_selection)
        self.utils.printGreen("Getting unmanaged clusters info...")
        isPrimary = len(domains["elements"][domain_index]['clusters']) == 0

        #Get Unmanaged Clusters
        unmanagedclusterspayload = {}
        unmanagedclusterspayload["name"] = UNMANAGED_CLUSTERS_CRITERION

        clusters_response = \
            self.clusters.get_unmanaged_clusters(
                unmanagedclusterspayload,
                domains_user_selection[domain_index]["id"])
        clustersqueriesurl = 'https://' + self.hostname + clusters_response.headers['Location']
        
        #Poll on get unmanaged clusters queries
        clusters_query_response = self.clusters.poll_queries(clustersqueriesurl)
        clusters_user_selection = list(map(lambda x: {"name": x['name']}, clusters_query_response["elements"]))
        print(*three_line_separator, sep='\n')
        clusters_selection_text = "Please choose the cluster:"
        clusters_index = self.let_user_pick(clusters_selection_text, clusters_user_selection)
        self.utils.printGreen("Getting cluster details...")

        # Get Unmanaged Cluster
        unmanagedclusterpayload = {}
        unmanagedclusterpayload["name"] = UNMANAGED_CLUSTER_CRITERION
        cluster_response = \
            self.clusters.get_unmanaged_cluster(
                unmanagedclusterpayload,
                domains_user_selection[domain_index]["id"],
                clusters_user_selection[clusters_index]["name"])

        clusterqueryurl = 'https://' + self.hostname + cluster_response.headers['Location']

        # Poll on get unmanaged cluster queries
        cluster_query_response = self.clusters.poll_queries(clusterqueryurl)
        time.sleep(5)

        #Hosts in the unmanaged cluster
        hosts_fqdn = list(map(lambda x: {"hostName": x['fqdn'], "ipAddress": x['ipAddress'], "vmNics": x['vmNics']},
                              cluster_query_response["elements"][0]["hosts"]))
        print(*three_line_separator, sep='\n')

        self.hosts.main_func(hosts_fqdn)
        # self.utils.printCyan("Below hosts are discovered. Enter the preconfigured root passwords for all esxis :")
        # self.utils.printYellow("**Entered password is applicable for all the hosts")
        # for idx, element in enumerate(hosts_fqdn):
        #     self.utils.printBold("{}) {}".format(idx + 1, element['hostName']))
        # hosts_password = self.utils.valid_input("\033[1m Enter hosts password: \033[0m", None, None, None, True)
        # while(hosts_password != self.utils.valid_input("\033[1m Confirm password: \033[0m",
        #                                                None, None, None, True)):
        #     self.utils.printRed("Passwords don't match")
        #     hosts_password = self.utils.valid_input("\033[1m Enter hosts password: \033[0m", None, None, None, True)

        existing_dvs_specs = cluster_query_response["elements"][0]["vdsSpecs"]
        is_existing_vds = False

        # print(*three_line_separator, sep='\n')
        self.utils.printCyan("System dvs for the discovered cluster:")
        for idx, element in enumerate(existing_dvs_specs):
            self.utils.printCyan("{}) {}".format(idx + 1, element['name']))

        #Get the system vds
        existing_dvs_spec = self.getSystemDvs(existing_dvs_specs)
        existing_dvs_spec_name = existing_dvs_spec['name']
        del existing_dvs_spec['niocBandwidthAllocationSpecs']

        dvs_selection_text = [{"name": "Create New DVS"}, {"name" : "Use Existing DVS"} ]

        print(*three_line_separator, sep='\n')
        dvs_helper_text = "Select the DVS option to proceed"
        dvs_index = self.let_user_pick(dvs_helper_text, dvs_selection_text)
        new_dvs_spec = {}
        vmNics = []
        if dvs_index == 0:
            self.utils.printGreen("Getting compatible vmnic information...")
            # Get Unmanaged Cluster
            compatiblevmnicpayload = {}
            compatiblevmnicpayload["name"] = MATCHING_VMNIC_CRITERION
            compatible_host_response = \
                self.clusters.get_unmanaged_cluster(
                    compatiblevmnicpayload,
                    domains_user_selection[domain_index]["id"],
                    clusters_user_selection[clusters_index]["name"])
            compatiblevmnicqueries = 'https://' + self.hostname + compatible_host_response.headers['Location']

            # Poll on get compatible cluster queries
            compatible_vmnic_response = self.clusters.poll_queries(compatiblevmnicqueries)
            hosts_pnics = compatible_vmnic_response["elements"][0]["hosts"]

            # Get used vmnics and map them to system vds
            if not isPrimary:
                vmnic_host = hosts_fqdn[0]["vmNics"]
                used_vmnics = list(filter(lambda x: x["isInUse"] == True, vmnic_host))
                vmNics = list(map(lambda x: {"id": x['name'], "vdsName": existing_dvs_spec_name}, used_vmnics))

            if len(hosts_pnics) > 0 and  "vmNics" in hosts_pnics[0] and len(hosts_pnics[0]["vmNics"]) > 1:
                is_existing_vds = False
                print(*three_line_separator, sep='\n')
                new_vds_name = input("\033[1m Enter the New DVS name : \033[0m")

                new_dvs_spec["name"] = new_vds_name
                new_dvs_spec["isUsedByNsxt"] = True

                vmnic_maps = list(map(lambda x: {"name": x['name'], "speed": str(x['linkSpeedMB']) + 'MB',
                                                 "active": "Active" if x['isActive'] else "Inactive"},
                                      hosts_pnics[0]["vmNics"]))

                print(*three_line_separator, sep='\n')
                self.utils.printCyan("Please choose the nics for overlay traffic:")
                self.utils.printBold("-----id---speed----status")
                self.utils.printBold("-------------------------")
                for idx, element in enumerate(vmnic_maps):
                    self.utils.printBold("{}) {}-{}-{}"
                                         .format(idx + 1,
                                                 element['name'],
                                                 element['speed'],
                                                 element['active']))

                is_correct_vmnic_selection = True

                while (is_correct_vmnic_selection):
                    try:
                        vmnic_options = list(map(int, input(
                            "\033[1m Enter your choices(minimum 2 numbers comma separated): \033[0m").strip().rstrip(
                            ",").split(
                            ',')))
                        while (len(vmnic_options) < 2):
                            self.utils.printRed(
                                'VMware High Availability (HA) requires a minimum of 2 vmnics. Select minimum 2 vmnics')
                            vmnic_options = list(map(int, input(
                                "\033[1m Enter your choices(minimum 2 numbers comma separated): \033[0m").strip().rstrip(
                                ",").split(
                                ',')))
                        print(*three_line_separator, sep='\n')
                        for index,elem in enumerate(vmnic_options):
                            temp_vmnic_info = {}
                            temp_vmnic_info['id'] = vmnic_maps[elem - 1]['name']
                            temp_vmnic_info['vdsName'] = new_vds_name
                            vmNics.append(temp_vmnic_info)
                        is_correct_vmnic_selection = False
                    except:
                        print(*three_line_separator, sep='\n')
                        self.utils.print_error("\033[1m Input a number between 1(included) and {0}(included)\033[0m"
                                               .format(str(len(vmnic_maps))))
                        is_correct_vmnic_selection = True
            else:
                self.utils.printRed(
                    'VMware High Availability (HA) requires a minimum of 2 vmnics. Found 0 or 1 vmnic')
                exit(1)

        elif dvs_index == 1:
            is_existing_vds = True
            dvs_names = list(map(lambda x: {"name": x['name']}, existing_dvs_specs))
            print(*three_line_separator, sep='\n')
            existing_dvs_helper = "Please select the existing dvs to continue with workload creation: "
            existing_dvs_index = self.let_user_pick(existing_dvs_helper, dvs_names)
            existing_dvs_spec = existing_dvs_specs[existing_dvs_index]
            existing_dvs_spec['isUsedByNsxt'] = True
            # del existing_dvs_spec['niocBandwidthAllocationSpecs']
            print(*three_line_separator, sep='\n')

        nsxt_payload = self.nsxt.main_func(domains_user_selection[domain_index]["id"], isPrimary)
        vxm_payload = self.vxrailmanager.main_func()
        licenses_payload = self.licenses.main_func()

        cluster_payload = {}
        if isPrimary:
            cluster_payload['clusterSpec'] = {}
            cluster_payload['clusterSpec']['name'] = clusters_user_selection[clusters_index]["name"]
            cluster_payload['clusterSpec']['vxRailDetails'] = vxm_payload
            cluster_payload['clusterSpec']['datastoreSpec'] = {
                "vsanDatastoreSpec": {
                    "licenseKey": licenses_payload['licenseKeys']['VSAN']
                }
            }
            cluster_payload['clusterSpec']['networkSpec'] = self.populatenetworkSpec(
                is_existing_vds, existing_dvs_spec, new_dvs_spec, nsxt_payload, isPrimary)
            cluster_payload['clusterSpec']['hostSpecs'] = self.hosts.populatehostSpec(is_existing_vds, hosts_fqdn,
                                                                                      vmNics)
            cluster_payload['nsxTSpec'] = self.populatensxtSpec(
                nsxt_payload, licenses_payload)

            cluster_payload_copy = copy.deepcopy(cluster_payload)
            self.maskPasswords(cluster_payload_copy)
            print(*three_line_separator, sep='\n')
            print (json.dumps(cluster_payload_copy, indent=2, sort_keys=True))
            input("\033[1m Enter to continue ...\033[0m")
            self.domains.update_workload_domain(cluster_payload, domains_user_selection[domain_index]["id"])

        else:
            cluster_payload['computeSpec'] = {}
            cluster_payload['computeSpec']['clusterSpecs'] = [{}]
            # cluster_payload['computeSpec']['clusterSpecs'].append({})
            cluster_payload['computeSpec']['clusterSpecs'][0]['datastoreSpec'] = {
                "vsanDatastoreSpec": {
                    "licenseKey": licenses_payload['licenseKeys']['VSAN']
                }
            }
            cluster_payload['computeSpec']['clusterSpecs'][0]['name'] = clusters_user_selection[clusters_index]["name"]
            cluster_payload['computeSpec']['clusterSpecs'][0]['networkSpec'] = self.populatenetworkSpec(
                is_existing_vds, existing_dvs_spec, new_dvs_spec, nsxt_payload, isPrimary)
            cluster_payload['computeSpec']['clusterSpecs'][0]['vxRailDetails'] = vxm_payload
            cluster_payload['computeSpec']['clusterSpecs'][0]['hostSpecs'] = self.hosts.populatehostSpec(
                is_existing_vds, hosts_fqdn, vmNics)
            cluster_payload['domainId'] = domains_user_selection[domain_index]["id"]

            cluster_payload_copy = copy.deepcopy(cluster_payload)
            self.maskPasswords(cluster_payload_copy)
            print(*three_line_separator, sep='\n')
            print (json.dumps(cluster_payload_copy, indent=2, sort_keys=True))
            input("\033[1m Enter to continue ...\033[0m")
            self.clusters.create_cluster(cluster_payload)

        exit(1)

if __name__ == "__main__":
    VxRaiWorkloadAutomator().initApp()
