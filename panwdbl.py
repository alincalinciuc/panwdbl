#
# Copyright (c) 2013-2015 Luigi Mori <l@isidora.org>
#
# Permission to use, copy, modify, and distribute this software for any
# purpose with or without fee is hereby granted, provided that the above
# copyright notice and this permission notice appear in all copies.
#
# THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
# WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
# ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
# WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
# ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
# OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
#

# Quick and dirty hub of public ip lists for Palo Alto Networks devices

import webapp2
import logging
import address
import types
import os
from google.appengine.ext.webapp import template
from google.appengine.api import memcache
from google.appengine.api import urlfetch
from google.appengine.ext import db
import lxml.html
import lxml.etree

class BlockList(db.Model):
    """DB model of iplist"""
    tag = db.StringProperty(required=True)
    time = db.DateTimeProperty(auto_now=True)
    iplist = db.StringListProperty(indexed=False, required=True)

class BlockListJob(webapp2.RequestHandler):
    """Base class for block list update jobs

    get method is periodically called by GAE as configured in cron.yml,
    unauthorized direct access is prevented via app.yaml
    """
    url = ""
    tag = "BlockListJobERROR"
    
    def handle_line(self, line):
        return address.create_address(line)
    
    def get(self):
        """Convert ip list retrieved from self.url into a list of IPs/NETs/RANGEs
        using address.optimize_list. The resulting iplist is then stored in the 
        GAE DataStore with tag self.tag. Memcache entry for the iplist is invalidated.
        """
        blist = urlfetch.fetch(self.url, deadline=60)
        if blist.status_code != 200:
            logging.error(self.tag+" returned: "+str(blist.status_code))
            self.response.headers['Content-Type'] = 'text/plain'
            self.response.write(self.tag+" returned: "+str(blist.status_code))
            return
        nets = set()
        for l in blist.content.splitlines():
            l = l.strip()
            if l == None or len(l) == 0:
                continue
            addr = self.handle_line(l)
            if addr == None:
                continue
            if type(addr) != types.ListType:
                addr = [addr]
            for a in addr:
                if not a in nets:
                    nets.add(a)
        nets = address.optimize_list([ x for x in nets ])
        
        self.response.headers['Content-Type'] = 'text/plain'
        self.response.write(self.tag+" list\n"+"# entries: "+str(len(nets))+"\n\n"+'\n'.join(map(repr, nets)))
        dblist = BlockList(tag=self.tag, iplist=map(repr, nets))
        dblist.put()
        memcache.delete("l"+self.tag)
        memcache.delete("t"+self.tag)
        logging.info(self.tag+" refreshed")
    
class SpamhausList(BlockListJob):
    """Base BlockListJob class for Spamhaus Lists"""
    url = ""
    tag = "SpamhausListERROR"
    
    def handle_line(self, line):
        if line[0] == ";":
            return None
        net = line.partition(";")[0]
        return address.create_address(net)
        
class SpamhausDrop(SpamhausList):
    url = "http://www.spamhaus.org/drop/drop.txt"
    tag = "SpamhausDROP"
    
class SpamhausEDrop(SpamhausList):
    url = "http://www.spamhaus.org/drop/edrop.txt"
    tag = "SpamhausEDROP"
        
class OpenBLIpList(BlockListJob):
    url = "http://www.openbl.org/lists/base.txt"
    tag = "OpenBLIpList"
    
    def handle_line(self, line):
        if line[0] == '#':
            return None
        return address.create_address(line)

class MalwareDomainList(BlockListJob):
    url = "http://www.malwaredomainlist.com/hostslist/ip.txt"
    tag = "MalwareDomainList"
        
class EmergingThreatsCompromisedList(BlockListJob):
    url = "http://rules.emergingthreats.net/open/suricata/rules/compromised-ips.txt"
    tag = "EmergingThreatsCompromisedList"
        
class BruteForceBlockerList(BlockListJob):
    url = "http://danger.rulez.sk/projects/bruteforceblocker/blist.php"
    tag = "BruteForceBlockerList"

    def handle_line(self, line):
        if line[0] == '#':
            return None
        return address.create_address(line)
        
class SnortRules(BlockListJob):
    """Base BlockListJob class for simple SnortRules block lists"""
    url = ""
    tag = "SnortRulesERROR"
    
    def handle_line(self, line):
        if line[0] == '#':
            return None
        source = line.split(None, 2)[2]
        if source[0] == '[':
            source = source[1:source.index(']')]
            source = source.split(',')
        else:
            source = [source]

        result = []
        for a in source:
            try:
                result.append(address.create_address(a))
            except:
                logging.exception('Error decoding: {!r}'.format(a))
                pass
        return result

class EmergingThreatsRBN(SnortRules):
    url = "http://rules.emergingthreats.net/blockrules/emerging-rbn-BLOCK.rules"
    tag = "EmergingThreatsRBN"
    
class EmergingThreatsTOR(SnortRules):
    url = "http://rules.emergingthreats.net/open/suricata/rules/tor.rules"
    tag = "EmergingThreatsTOR"
    
class DshieldBlockList(BlockListJob):
    url = "http://feeds.dshield.org/block.txt"
    tag = "DshieldBlockList"
    
    def handle_line(self, line):
        if line[0] == '#':
            return None
        if line[0] == 'S':
            return None
        start, end = line.split()[:2]
        return address.create_address(start+"-"+end)

class SSLAbuseIPList(BlockListJob):
    url = "https://sslbl.abuse.ch/blacklist/sslipblacklist.csv"
    tag = "SSLAbuseIPList"
    
    def handle_line(self, line):
        if line[0] == "#":
            return None
        net = line.split(",")[0]
        return address.create_address(net)

class ZeusTrackerBadIPsList(BlockListJob):
    url = "https://zeustracker.abuse.ch/blocklist.php?download=badips"
    tag = "ZeusTrackerBadIPsList"
    
    def handle_line(self, line):
        if line[0] == '#':
            return None
        return address.create_address(line)

class TalosIntelIPFilter(BlockListJob):
    url = "http://talosintel.com/feeds/ip-filter.blf"
    tag = "TalosIntelIPFilter"

class Office365NetBlocks(webapp2.RequestHandler):
    """Not used, MS web page is unreliable, includes ProPlus, Office Online and RCA"""
    url = "https://support.content.office.net/en-us/static/O365IPAddresses.xml"
    tag = "Office365NetBlocks"
    
    def get(self):
        page = urlfetch.fetch(self.url, deadline=60)
        if page.status_code != 200:
            logging.error(self.tag+" returned: "+str(page.status_code))
            self.response.headers['Content-Type'] = 'text/plain'
            self.response.write(self.tag+" returned: "+str(page.status_code))
            return
        ltree = lxml.etree.fromstring(page.content)

        nets = set()

        ipv4 = ltree.xpath("/products/product[@name='o365']/addresslist[@type='IPv4']/address")
        for a in ipv4:
            addr = address.create_address(a.text)
            if addr == None:
                continue
            if type(addr) != types.ListType:
                addr = [addr]
            for a in addr:
                if not a in nets:
                    nets.add(a)

        ipv4 = ltree.xpath("/products/product[@name='ProPlus']/addresslist[@type='IPv4']/address")
        for a in ipv4:
            addr = address.create_address(a.text)
            if addr == None:
                continue
            if type(addr) != types.ListType:
                addr = [addr]
            for a in addr:
                if not a in nets:
                    nets.add(a)

        ipv4 = ltree.xpath("/products/product[@name='RCA']/addresslist[@type='IPv4']/address")
        for a in ipv4:
            addr = address.create_address(a.text)
            if addr == None:
                continue
            if type(addr) != types.ListType:
                addr = [addr]
            for a in addr:
                if not a in nets:
                    nets.add(a)

        ipv4 = ltree.xpath("/products/product[@name='WAC']/addresslist[@type='IPv4']/address")
        for a in ipv4:
            addr = address.create_address(a.text)
            if addr == None:
                continue
            if type(addr) != types.ListType:
                addr = [addr]
            for a in addr:
                if not a in nets:
                    nets.add(a)

        nets = address.optimize_list([ x for x in nets ])

        self.response.headers['Content-Type'] = 'text/plain'
        self.response.write(self.tag+" list\n"+"# entries: "+str(len(nets))+"\n\n"+'\n'.join(map(repr, nets)))
        dblist = BlockList(tag=self.tag, iplist=map(repr, nets))
        dblist.put()
        memcache.delete("l"+self.tag)
        memcache.delete("t"+self.tag)
        logging.info(self.tag+" refreshed")

class ExchangeOnlineNetBlocks(webapp2.RequestHandler):
    """Not used, MS web page is unreliable, includes Exchange Online Protection"""
    url = "https://support.content.office.net/en-us/static/O365IPAddresses.xml"
    tag = "ExchangeOnlineNetBlocks"
    
    def get(self):
        page = urlfetch.fetch(self.url, deadline=60)
        if page.status_code != 200:
            logging.error(self.tag+" returned: "+str(page.status_code))
            self.response.headers['Content-Type'] = 'text/plain'
            self.response.write(self.tag+" returned: "+str(page.status_code))
            return
        ltree = lxml.etree.fromstring(page.content)

        nets = set()

        ipv4 = ltree.xpath("/products/product[@name='EXO']/addresslist[@type='IPv4']/address")
        for a in ipv4:
            addr = address.create_address(a.text)
            if addr == None:
                continue
            if type(addr) != types.ListType:
                addr = [addr]
            for a in addr:
                if not a in nets:
                    nets.add(a)

        ipv4 = ltree.xpath("/products/product[@name='EOP']/addresslist[@type='IPv4']/address")
        for a in ipv4:
            addr = address.create_address(a.text)
            if addr == None:
                continue
            if type(addr) != types.ListType:
                addr = [addr]
            for a in addr:
                if not a in nets:
                    nets.add(a)
        nets = address.optimize_list([ x for x in nets ])
        
        self.response.headers['Content-Type'] = 'text/plain'
        self.response.write(self.tag+" list\n"+"# entries: "+str(len(nets))+"\n\n"+'\n'.join(map(repr, nets)))
        dblist = BlockList(tag=self.tag, iplist=map(repr, nets))
        dblist.put()
        memcache.delete("l"+self.tag)
        memcache.delete("t"+self.tag)
        logging.info(self.tag+" refreshed")

class LyncOnlineNetBlocks(webapp2.RequestHandler):
    """Not used, MS web page is unreliable, includes Skype for Business Online"""
    url = "https://support.content.office.net/en-us/static/O365IPAddresses.xml"
    tag = "LyncOnlineNetBlocks"
    
    def get(self):
        page = urlfetch.fetch(self.url, deadline=60)
        if page.status_code != 200:
            logging.error(self.tag+" returned: "+str(page.status_code))
            self.response.headers['Content-Type'] = 'text/plain'
            self.response.write(self.tag+" returned: "+str(page.status_code))
            return
        ltree = lxml.etree.fromstring(page.content)

        nets = set()

        ipv4 = ltree.xpath("/products/product[@name='LYO']/addresslist[@type='IPv4']/address")
        for a in ipv4:
            addr = address.create_address(a.text)
            if addr == None:
                continue
            if type(addr) != types.ListType:
                addr = [addr]
            for a in addr:
                if not a in nets:
                    nets.add(a)
        nets = address.optimize_list([ x for x in nets ])
        
        self.response.headers['Content-Type'] = 'text/plain'
        self.response.write(self.tag+" list\n"+"# entries: "+str(len(nets))+"\n\n"+'\n'.join(map(repr, nets)))
        dblist = BlockList(tag=self.tag, iplist=map(repr, nets))
        dblist.put()
        memcache.delete("l"+self.tag)
        memcache.delete("t"+self.tag)
        logging.info(self.tag+" refreshed")

class SharepointOnlineNetBlocks(webapp2.RequestHandler):
    """Not used, MS web page is unreliable"""
    url = "https://support.content.office.net/en-us/static/O365IPAddresses.xml"
    tag = "SharepointOnlineNetBlocks"
    
    def get(self):
        page = urlfetch.fetch(self.url, deadline=60)
        if page.status_code != 200:
            logging.error(self.tag+" returned: "+str(page.status_code))
            self.response.headers['Content-Type'] = 'text/plain'
            self.response.write(self.tag+" returned: "+str(page.status_code))
            return
        ltree = lxml.etree.fromstring(page.content)

        nets = set()

        ipv4 = ltree.xpath("/products/product[@name='SPO']/addresslist[@type='IPv4']/address")
        for a in ipv4:
            addr = address.create_address(a.text)
            if addr == None:
                continue
            if type(addr) != types.ListType:
                addr = [addr]
            for a in addr:
                if not a in nets:
                    nets.add(a)
        nets = address.optimize_list([ x for x in nets ])
        
        self.response.headers['Content-Type'] = 'text/plain'
        self.response.write(self.tag+" list\n"+"# entries: "+str(len(nets))+"\n\n"+'\n'.join(map(repr, nets)))
        dblist = BlockList(tag=self.tag, iplist=map(repr, nets))
        dblist.put()
        memcache.delete("l"+self.tag)
        memcache.delete("t"+self.tag)
        logging.info(self.tag+" refreshed")

class GetBlockList(webapp2.RequestHandler):
    """Base class for ip list retrive requests"""
    tag = "GetBlockListERROR"
    copyright = None

    def __get_iplist(self):
        iplist = memcache.get("l"+self.tag)
        if iplist is not None:
            ipltime = memcache.get("t"+self.tag)
            return ipltime, iplist

        q = BlockList.all()
        q.filter("tag =", self.tag)
        q.order("-time")
        iplist = q.get()

        if iplist is None:
            iplist = []
            ipltime = None
        else:
            ipltime = iplist.time.strftime('%d %b %Y %H:%M %Z')
            iplist = iplist.iplist

        memcache.set("t"+self.tag, ipltime, 60*60*24)
        memcache.set("l"+self.tag, iplist, 60*60*24)

        return ipltime, iplist
            
    def get(self):
        ipltime, iplist = self.__get_iplist()

        n = self.request.get('n', None)
        if n is None:
            n = len(iplist)
        else:
            try:
                n = int(n)
            except:
                logging.error("Invalid value for n: %s", n)
                n = len(iplist)
            if n < 0:
                logging.error("Invalid value for n: %d", n)
                n = len(iplist)
        s = self.request.get('s', None)
        if s is None:
            s = 0
        else:
            try:
                s = int(s)
            except:
                logging.error("Invalid value for s: %s", s)
                s = 0
            if s < 0:
                logging.error("Invalid value for s: %s", s)
                s = 0

        self.response.headers['Content-Type'] = 'text/plain'

        if ipltime is not None or self.copyright is not None:
            header = '#'
            if self.copyright is not None:
                header += ' '+self.copyright
            if ipltime is not None:
                header += ' Retrieved: %s'%ipltime
            self.response.write('%s\n' % header)

        self.response.write('\n'.join(iplist[s:s+n]))  
        
class GetEmergingThreatsRBN(GetBlockList):
    tag = "EmergingThreatsRBN"
    
class GetSpamhausDrop(GetBlockList):
    copyright = "Spamhaus DROP (c) Do not use after 2 days."
    tag = "SpamhausDROP"
        
class GetSpamhausEDrop(GetBlockList):
    copyright = "Spamhaus EDROP (c) Do not use after 2 days."
    tag = "SpamhausEDROP"
    
class GetOpenBLIpList(GetBlockList):
    tag = "OpenBLIpList"

class GetMalwareDomainList(GetBlockList):
    tag = "MalwareDomainList"
    
class GetEmergingThreatsCompromisedList(GetBlockList):
    tag = "EmergingThreatsCompromisedList"
    
class GetBruteForceBlockerList(GetBlockList):
    tag = "BruteForceBlockerList"
    
class GetEmergingThreatsTOR(GetBlockList):
    tag = "EmergingThreatsTOR"
    
class GetDshieldBlockList(GetBlockList):    
    tag = "DshieldBlockList"

class GetGoogleNetBlocks(GetBlockList):
    tag = "GoogleNetBlocks"

class GetSSLAbuseIPList(GetBlockList):
    tag = "SSLAbuseIPList"

class GetZeusTrackerBadIPsList(GetBlockList):
    tag = "ZeusTrackerBadIPsList"

class GetTalosIntelIPFilter(GetBlockList):
    tag = "TalosIntelIPFilter"

class MainPage(webapp2.RequestHandler):
    """Main page renderer"""
    def __get_iplist_info(self, tag):
        ipltime = memcache.get("t"+tag)
        iplist = memcache.get("l"+tag)
        if (ipltime is not None) and (iplist is not None):
            iplist = len(iplist)
            return ipltime, iplist
        else:
            q = BlockList.all()
            q.filter("tag =", tag)
            q.order("-time")
            iplist = q.get()
            if iplist is None:
                return '--', '--'
            else:
                ipltime = iplist.time.strftime('%d %b %Y %H:%M %Z')
                memcache.set_multi({"t"+tag: ipltime, "l"+tag: iplist.iplist}, 60*60*24)
                return ipltime, len(iplist.iplist)
        
    def get(self):
        tags = ["EmergingThreatsRBN",
                "SpamhausDROP",
                "SpamhausEDROP",
                "OpenBLIpList",
                "MalwareDomainList",
                "EmergingThreatsCompromisedList",
                "BruteForceBlockerList",
                "EmergingThreatsTOR",
                "DshieldBlockList",
                "SSLAbuseIPList",
                "ZeusTrackerBadIPsList"]
        template_values = {}
        
        for t in tags:
            ipld, ipln = self.__get_iplist_info(t)
            template_values['n'+t] = ipln
            template_values['d'+t] = ipld
                
        path = os.path.join(os.path.dirname(__file__), 'index.html')
        self.response.out.write(template.render(path, template_values))

app = webapp2.WSGIApplication([('/', MainPage),
                                ('/jobs/shdropjob', SpamhausDrop),
                                ('/jobs/shedropjob', SpamhausEDrop),
                                ('/jobs/mdljob', MalwareDomainList),
#                                ('/jobs/openbljob', OpenBLIpList),
                                ('/jobs/bruteforceblockerjob', BruteForceBlockerList),
                                ('/jobs/etrbnjob', EmergingThreatsRBN),
                                ('/jobs/ettorjob', EmergingThreatsTOR),
                                ('/jobs/etcompromisedjob', EmergingThreatsCompromisedList),
                                ('/jobs/dshieldbljob', DshieldBlockList),
                                ('/jobs/sslabuseiplistjob', SSLAbuseIPList),
                                ('/jobs/zeustrackerbadipsjob', ZeusTrackerBadIPsList),
                                # ('/jobs/office365netblocksjob', Office365NetBlocks),
                                # ('/jobs/exchangeonlinenetblocksjob', ExchangeOnlineNetBlocks),
                                # ('/jobs/lynconlinenetblocksjob', LyncOnlineNetBlocks),
                                # ('/jobs/sharepointonlinenetblocksjob', SharepointOnlineNetBlocks),
                                ('/jobs/talosintelipfilterjob', TalosIntelIPFilter),
                                ('/lists/shdrop.txt', GetSpamhausDrop),
                                ('/lists/shedrop.txt', GetSpamhausEDrop),
                                ('/lists/mdl.txt', GetMalwareDomainList),
#                                ('/lists/openbl.txt', GetOpenBLIpList),
                                ('/lists/bruteforceblocker.txt', GetBruteForceBlockerList),
                                ('/lists/etrbn.txt', GetEmergingThreatsRBN),
                                ('/lists/ettor.txt', GetEmergingThreatsTOR),
                                ('/lists/etcompromised.txt', GetEmergingThreatsCompromisedList),
                                ('/lists/dshieldbl.txt', GetDshieldBlockList),
                                ('/lists/sslabuseiplist.txt', GetSSLAbuseIPList),
                                ('/lists/zeustrackerbadips.txt', GetZeusTrackerBadIPsList),
                                # ('/lists/office365netblocks.txt', GetOffice365NetBlocks),
                                # ('/lists/exchangeonlinenetblocks.txt', GetExchangeOnlineNetBlocks),
                                # ('/lists/lynconlinenetblocks.txt', GetLyncOnlineNetBlocks),
                                # ('/lists/sharepointonlinenetblocks.txt', GetSharepointOnlineNetBlocks),
                                ('/lists/talosintelipfilter.txt', GetTalosIntelIPFilter)
                                ],
                              debug=False)
