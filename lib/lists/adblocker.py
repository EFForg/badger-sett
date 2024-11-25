#!/usr/bin/env python3

import os
import re

from lib.basedomain import extract
from lib.lists.blocklist import Blocklist


class Adblocker(Blocklist):

    list_urls = (
        "https://easylist.to/easylist/easylist.txt",
        "https://easylist.to/easylist/easyprivacy.txt",

        ("https://pgl.yoyo.org/adservers/serverlist.php?hostformat=adblockplus&showintro=0&mimetype=plaintext",
         "peterlowe.txt"),

        ("https://ublockorigin.github.io/uAssets/filters/filters.txt",
         "uAssets-filters.txt"),
        ("https://ublockorigin.github.io/uAssets/filters/filters-2020.txt",
         "uAssets-filters-2020.txt"),
        ("https://ublockorigin.github.io/uAssets/filters/filters-2021.txt",
         "uAssets-filters-2021.txt"),
        ("https://ublockorigin.github.io/uAssets/filters/filters-2022.txt",
         "uAssets-filters-2022.txt"),
        ("https://ublockorigin.github.io/uAssets/filters/filters-2023.txt",
         "uAssets-filters-2023.txt"),
        ("https://ublockorigin.github.io/uAssets/filters/filters-2024.txt",
         "uAssets-filters-2024.txt"),
        ("https://ublockorigin.github.io/uAssets/filters/privacy.txt",
         "uAssets-privacy.txt"),

        # uBO regional lists
        "https://raw.githubusercontent.com/AnXh3L0/blocklist/master/albanian-easylist-addition/Albania.txt",
        ("https://easylist-downloads.adblockplus.org/liste_ar.txt",
         "arabic.txt"),
        ("https://stanev.org/abp/adblock_bg.txt", "bulgarian.txt"),
        ("https://filters.adtidy.org/extension/ublock/filters/224.txt",
         "chinese.txt"),
        ("https://raw.githubusercontent.com/tomasko126/easylistczechandslovak/master/filters.txt",
         "czechandslovak.txt"),
        "https://easylist.to/easylistgermany/easylistgermany.txt",
        #("https://adblock.ee/list.txt", "estonian.txt"),
        "https://raw.githubusercontent.com/finnish-easylist-addition/finnish-easylist-addition/gh-pages/Finland_adb.txt",
        ("https://filters.adtidy.org/extension/ublock/filters/16.txt",
         "french.txt"),
        ("https://www.void.gr/kargig/void-gr-filters.txt", "greek.txt"),
        "https://raw.githubusercontent.com/DandelionSprout/adfilt/master/SerboCroatianList.txt",
        "https://cdn.jsdelivr.net/gh/hufilter/hufilter@gh-pages/hufilter-ublock.txt",
        ("https://raw.githubusercontent.com/ABPindo/indonesianadblockrules/master/subscriptions/abpindo.txt",
         "indonesiaandmalaysia.txt"),
        "https://easylist-downloads.adblockplus.org/indianlist.txt",
        "https://raw.githubusercontent.com/MasterKia/PersianBlocker/main/PersianBlocker.txt",
        ("https://raw.githubusercontent.com/brave/adblock-lists/master/custom/is.txt",
         "icelandic.txt"),
        "https://raw.githubusercontent.com/easylist/EasyListHebrew/master/EasyListHebrew.txt",
        "https://easylist-downloads.adblockplus.org/easylistitaly.txt",
        ("https://filters.adtidy.org/extension/ublock/filters/7.txt",
         "japanese.txt"),
        ("https://cdn.jsdelivr.net/gh/List-KR/List-KR@latest/filters-share/3rd_domains.txt",
         "korean1.txt"),
        ("https://cdn.jsdelivr.net/gh/List-KR/List-KR@latest/filters-share/1st_domains.txt",
         "korean2.txt"),
        "https://raw.githubusercontent.com/EasyList-Lithuania/easylist_lithuania/master/easylistlithuania.txt",
        "https://raw.githubusercontent.com/Latvian-List/adblock-latvian/master/lists/latvian-list.txt",
        ("https://raw.githubusercontent.com/DeepSpaceHarbor/Macedonian-adBlock-Filters/master/Filters",
         "macedonian.txt"),
        ("https://filters.adtidy.org/extension/ublock/filters/8.txt",
         "dutch.txt"),
        "https://raw.githubusercontent.com/DandelionSprout/adfilt/master/NorwegianList.txt",
        ("https://raw.githubusercontent.com/MajkiIT/polish-ads-filter/master/polish-adblock-filters/adblock.txt",
         "polish.txt"),
        ("https://raw.githubusercontent.com/tcptomato/ROad-Block/master/road-block-filters-light.txt",
         "romanian.txt"),
        ("https://raw.githubusercontent.com/easylist/ruadlist/master/advblock/adservers.txt",
         "russian1.txt"),
        ("https://raw.githubusercontent.com/easylist/ruadlist/master/advblock/thirdparty.txt",
         "russian2.txt"),
        "https://easylist-downloads.adblockplus.org/easylistspanish.txt",
        ("https://filters.adtidy.org/extension/ublock/filters/9.txt",
         "spanishandportuguese.txt"),
        ("https://raw.githubusercontent.com/betterwebleon/slovenian-list/master/filters.txt",
         "slovenian.txt"),
        "https://raw.githubusercontent.com/lassekongo83/Frellwits-filter-lists/master/Frellwits-Swedish-Filter.txt",
        "https://raw.githubusercontent.com/easylist-thailand/easylist-thailand/master/subscription/easylist-thailand.txt",
        ("https://filters.adtidy.org/extension/ublock/filters/13.txt",
         "turkish.txt"),
        ("https://raw.githubusercontent.com/abpvn/abpvn/master/filter/abpvn_ublock.txt",
         "vietnamese.txt"),
    )

    domain_filter_suffixes = ("^", "^$document", "^$document,popup", "^$popup",
                              "^$popup,third-party", "^$script,third-party",
                              "^$script", "^$third-party")

    first_party_subdomains = ("smetrics.", "marketing.", "metrics.", "stats.")

    valid_domain_re = re.compile(r'^[A-Za-z0-9\.-]+$')

    bases = set()
    domains = set()

    def process_line(self, line):
        if not line.startswith("||"):
            return False

        # TODO review filter suffixes
        if line.endswith(self.domain_filter_suffixes) or self.valid_domain_re.match(line[2:]):
            domain = line[2:line.rfind("^")]

            if domain.startswith(self.first_party_subdomains):
                return False

            # TODO review this charset
            if not self.valid_domain_re.match(domain):
                return False

            base = extract(domain).registered_domain
            if not base:
                return False

            self.bases.add(base)
            self.domains.add(domain)

            return True

        return False

    def ingest_list(self, url, filename):
        if not filename:
            filename = url.rpartition('/')[-1]

        filename = os.path.join(self.cache_dir, filename)

        self.fetch(url, filename)

        try:
            with open(filename, encoding='utf-8') as file:
                # TODO check for !#include statements
                count = 0
                for line in file:
                    if self.process_line(line.rstrip()):
                        count += 1
                if count == 0:
                    print(f"WARNING No domains found in {filename}")
        except FileNotFoundError:
            # if the (re)download failed for whatever reason
            print(f"WARNING Failed to open {filename}")
            return False

        return True

    def __init__(self):
        for url in self.list_urls:
            filename = None
            if len(url) == 2:
                filename = url[1]
                url = url[0]
            if not self.ingest_list(url, filename):
                return

        self.ready = True
