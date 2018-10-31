#!/usr/bin/env python3
from collections import defaultdict
import sys
import requests
import json
import yaml
import xmltodict
import ipaddress

QUERY_FULLTEXT = "fulltext"
QUERY_ORG = "org"


def query_fulltext(query):
    def nets_from_list(listing):
        net = None
        netname = None
        desc = None

        for entry in listing:
            for kv in entry['str']:
                if kv['@name'] == 'lookup-key':
                    net = kv['#text']
                elif kv['@name'] == 'descr':
                    desc = kv['#text']
                elif kv['@name'] == 'netname':
                    netname = kv['#text']
            yield (net, netname, desc)

    payload = {
        'start': 0,
    }

    response = requests.get(
        'https://apps.db.ripe.net/db-web-ui/api/rest/fulltextsearch/select?q={0}'.format(query),
        params=payload
    )

    o = xmltodict.parse(response.text)
    max = int(o['response']['result']['@numFound'])
    payload['start'] = len(o['response']['result']['doc'])

    for cidr, netname, desc in nets_from_list(o['response']['result']['doc']):
        yield (cidr, netname, desc)

    while payload['start'] < max:
        response = requests.get(
            'https://apps.db.ripe.net/db-web-ui/api/rest/fulltextsearch/select?q={0}'.format(query),
            params=payload
        )

        o = xmltodict.parse(response.text)
        payload['start'] += len(o['response']['result']['doc'])

        for cidr, netname, desc in nets_from_list(o['response']['result']['doc']):
            if '-' in cidr:
                first, last = map(ipaddress.ip_address, cidr.split(' - '))
                cidr = list(ipaddress.summarize_address_range(first, last))[0]
            yield (cidr, netname, desc)


def query_inetnums_by_org(org):
    payload = {
        'query-string': org,
        'inverse-attribute': 'org',
        'type-filter': ['inetnum', 'inet6num'],
        'source': 'RIPE',
        'flags': ['no-irt', 'no-referenced']
    }
    response = requests.get(
        'https://rest.db.ripe.net/search.json', params=payload
    ).json()

    for entry in response['objects']['object']:
        cidr = entry['primary-key']['attribute'][0]['value']
        netname = None
        desc = None

        if '-' in cidr:
            first, last = map(ipaddress.ip_address, cidr.split(' - '))
            cidr = list(ipaddress.summarize_address_range(first, last))[0]

        for item in entry['attributes']['attribute']:
            if item['name'] == 'netname':
                netname = item['value']
            if item['name'] == 'descr':
                desc = item['value']

        yield (cidr, netname, desc)


if __name__ == '__main__':
    # TODO: argparser
    if len(sys.argv) < 2:
        print("usage: lookup.py <queryfile>")
        sys.exit(1)

    with open(sys.argv[1]) as handle:
        queries = yaml.load(handle)['queries']

    results = defaultdict(list)
    for institute in queries:
        for query in institute['queries']:
            if query['type'] == QUERY_FULLTEXT:
                for net, netname, desc in query_fulltext(query['value']):
                    results[institute['owner']].append(
                        {'cidr': str(net), 'netname': netname, 'desc': desc}
                    )

            elif query['type'] == QUERY_ORG:
                for net, netname, desc in query_inetnums_by_org(query['value']):
                    results[institute['owner']].append(
                        {'cidr': str(net), 'netname': netname, 'desc': desc}
                    )

    print(json.dumps(results, indent=2))


