import requests
import json


if __name__ == "__main__":
    account_id = '2017740247'
    url = f'http://vortex.worldofwarships.asia/api/accounts/{account_id}/ships/pvp/'
    resp = requests.get(url)
    data = resp.json()
    data = data['data'][account_id]['statistics']
    result = 0
    for ship_id, ship_data in data.items():
        type = 'pvp'
        if 'damage_dealt' in ship_data[type]:
            result+=ship_data[type]['planes_killed']
    print(result)

# if __name__ == "__main__":
#     account_id = '2017740247'
#     url = f'https://api.worldofwarships.asia/wows/ships/stats/?application_id=aaaa630bfc681dfdbc13c3327eac2e85&account_id=2017740247&extra=pvp_solo'
#     resp = requests.get(url)
#     data = resp.json()
#     data = data['data'][account_id]
#     result = 0
#     for ship_data in data:
#         result+=ship_data['battles']
#     print(result)
