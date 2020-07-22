
import getpass
from Utils.utils import Utils


class HostsAutomator:
    def __init__(self, args):
        self.utils = Utils(args)
        self.password_map = {}

    def main_func(self, hosts_fqdn):
        three_line_separator = ['', '', '']
        self.utils.printCyan("Below hosts are discovered. Enter the password for them:")
        hostls = []
        for idx, element in enumerate(hosts_fqdn):
            self.utils.printBold("{}) {}".format(idx + 1, element['hostName']))
            hostls.append(element['hostName'])

        print(*three_line_separator, sep='\n')

        self.utils.printCyan("Please choose password option:")
        self.utils.printBold("1) Input one password that is applicable to all the hosts (default)")
        self.utils.printBold("2) Input password individually for each host")
        theoption = self.utils.valid_input("\033[1m Enter your choice(number): \033[0m", "1", self.__valid_option, ["1", "2"])

        print(*three_line_separator, sep='\n')
        if theoption == "1":
            self._option1(hostls)
        else:
            self._option2(hostls)

    def _option1(self, hostls):
        three_line_separator = ['', '', '']
        pwd = self.__handle_password_input()
        for hnm in hostls:
            self.password_map[hnm] = pwd
        print(*three_line_separator, sep='\n')

    def _option2(self, hostls):
        three_line_separator = ['', '', '']
        for hnm in hostls:
            self.utils.printCyan("Input root password of host {}".format(hnm))
            self.password_map[hnm] = self.__handle_password_input()
            print(*three_line_separator, sep='\n')


    def __valid_option(self, inputstr, choices):
        choice = str(inputstr).strip().lower()
        if choice in choices:
            return choice
        self.utils.printYellow("**Use first choice by default")
        return list(choices)[0]

    def __handle_password_input(self):
        while(True):
            thepwd = getpass.getpass("\033[1m Enter root password: \033[0m")
            confirmpwd = getpass.getpass("\033[1m Confirm password: \033[0m")
            if thepwd != confirmpwd:
                self.utils.printRed("Passwords don't match")
            else:
                return thepwd

    def populatehostSpec(self, isExistingDvs = True, hostsSpec = None, vmNics = None):
        uname = "root"
        temp_hosts_spec = []
        for element in hostsSpec:
            hostSpec = {}
            hostSpec['ipAddress'] = element['ipAddress']
            hostSpec['hostName'] = element['hostName']
            hostSpec['username'] = uname
            hostSpec['password'] = self.password_map[element['hostName']]
            if not isExistingDvs:
                hostSpec['hostNetworkSpec']= {
                    "vmNics": vmNics
                }
            temp_hosts_spec.append(hostSpec)
        return temp_hosts_spec