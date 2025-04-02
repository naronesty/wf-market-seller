import requests
import sys
import json
from dataclasses import dataclass

BASE_URL = "https://api.warframe.market/v1"
CREDENTIAL_FILE = "credentials.json"
SELL_LIST_FILE = "sell_list.txt"
SELL_LIST_INDENT = 2
DEFAULT_MIN_PRICE = 9

@dataclass
class LineInfo:
    item_name: str
    rank: int
    min_price: int
    quantity: int

@dataclass
class MarketOrder:
    id: str
    item_id: str
    item_name: str
    item_url_name: str
    platinum: int
    rank: int
    quantity: int

def login(email: str, password: str, csrf: str, cookie:str) -> str:
    '''
    Logs in to Warframe Market and returns a session token
    '''
    # csrf_token = get_csrf_token()
    url = f"{BASE_URL}/auth/signin"
    payload = {"auth_type": "cookie", "email": email, "password": password}
    headers = {
        "x-csrftoken": csrf,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Platform": "pc",
        "Language": "en",
        "Cookie": cookie
    }

    response = requests.post(url, json=payload, headers=headers)    

    if response.status_code == 200:
        token = response.cookies.get("JWT")
        if token:
            print("[+] Login successful!")
            return token
        else:
            raise ValueError("Failed to retrieve authentication token.")
    else:
        raise ValueError(f"Login failed: {response.status_code} - {response.text}")
    
def get_item_id(item_name: str) -> str:
    '''
    Retrieves the item ID for the given item name
    '''
    url = f"{BASE_URL}/items/{item_name}"
    response = requests.get(url)

    if response.status_code == 200:
        data = response.json()
        return data["payload"]["item"]["id"]
    else:
        print(f"[!] Error: failed to get [{item_name}] ID: {response.status_code} - {response.text}")
    
def get_price(item_name: str, min_price: int) -> int:
    '''
    Gets the lowest sell order platinum price for an item from a user who is online-in-game or the minimum price for that item
    '''    
    url = f"{BASE_URL}/items/{item_name}/orders"
    response = requests.get(url)

    if response.status_code != 200:
        raise ValueError(f"Failed to fetch orders: {response.status_code} - {response.text}")

    data = response.json()
    orders = data.get("payload", {}).get("orders", [])

    # Filter for "sell" orders from users who are "ingame"
    ingame_sell_orders = [
        order for order in orders
        if order.get("order_type") == "sell" and order.get("user", {}).get("status") == "ingame"
    ]

    # Get the lowest platinum price among valid orders
    if ingame_sell_orders:
        lowest_price = min(order["platinum"] for order in ingame_sell_orders)
        print(f"[+] Lowest price for {item_name.replace('_', ' ').title()}: {lowest_price} platinum")
        
        price = max(lowest_price, min_price)
        if price != lowest_price: print (f"    [!] Under minimum price of {min_price}: {lowest_price}")
        print(f"    [i] Selling for {price} platinum")
        
        return price
    else:
        print(f"[!] Error: no in-game sell orders for [{item_name}]")


def create_sell_order(token: str, item_id: str, platinum: int, quantity: int, rank: int, username: str) -> None:
    '''
    Creates a sell order for the given item
    '''
    url = f"{BASE_URL}/profile/orders"
    headers = {
        "Authorization": f"JWT {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Platform": "pc",
        "Language": "en",
    }

    if rank == None:
        order_payload = {
        "order_type": "sell",
        "item_id": item_id,
        "platinum": platinum,
        "quantity": quantity,
        "visible": True
        }
    else: 
        order_payload = {
            "order_type": "sell",
            "item_id": item_id,
            "platinum": platinum,
            "quantity": quantity,
            "rank": rank,
            "visible": True
        }
    
    update_payload = {
        "quantity": quantity
    }

    response = requests.post(url, json=order_payload, headers=headers)

    if response.status_code == 200:
        print("    [+] Sell order created successfully!")
    else:
        print("    [!] Error: order already exists.")
        orders_by_item_id = get_orders_by_attr(username, "item_id")
        print(f"        [+] Got sell orders for user: {username}")
        print("            Attempting to update order...")
        response = requests.put(f"{url}/{orders_by_item_id[item_id][0].id}", headers=headers, json=update_payload)
        if response.status_code == 200:
            print("    [+] Sell order updated successfully!")
        else:
            print(f"    [!] Update failed: {response.status_code} - {response.text}")
        

def parse_line(line: str) -> LineInfo:
    '''
    Parses a line of the SELL_LIST_FILE into a dictionary with the item name, quantity, rank and min price
    '''
    info = LineInfo("", None, None, None)
    line = line.strip()
    if line.startswith("+"):
        line = line[1:].strip()
        
        # Get item quantity, rank and min price
        linelist = line.split()
        for item in reversed(linelist):
            if item.isdigit():
                info.quantity = int(item)
            elif item.startswith("r") and item[1:].isdigit():
                info.rank = int(item[1:])
            elif item.startswith("min") and item[3:].isdigit():
                info.min_price = int(item[3:])
                
        if info.quantity != None:
            del linelist[-1]
        if info.rank != None:
            del linelist[-1]
        if info.min_price != None:
            del linelist[-1]
        
        info.item_name = " ".join(linelist).title()
        return info
    

def run_seller(token: str, username: str):
    '''
    Creates sell orders with items and specificiations listed in the SELL_LIST_FILE
    '''
    with open(SELL_LIST_FILE, "r") as file:
        for line in file:
            info = parse_line(line)
            if info:
                info.item_name = info.item_name.lower().replace(' ', '_').replace('orokin', 'corrupted')
                if info.min_price == None: info.min_price = DEFAULT_MIN_PRICE
                if info.quantity == None: info.quantity = 1
                item_id = get_item_id(info.item_name)
                if not item_id: continue
                
                # Get the lowest reasonable in-game sell order price and create the sell order
                plat_price = get_price(info.item_name, info.min_price)
                if not plat_price: continue
                create_sell_order(token, item_id, plat_price, info.quantity, info.rank, username)
        
def delete_sell_order(token: str, order_id: str):
    '''
    Deletes a sell order from the user's Warframe Market profile.
    '''
    url = f"{BASE_URL}/profile/orders/{order_id}"
    headers = {
        "Authorization": f"JWT {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Platform": "pc",
        "Language": "en",
    }

    response = requests.delete(url, headers=headers)

    if response.status_code == 200:
        print(f"[+] Successfully deleted sell order with ID: {order_id}")
    else:
        raise ValueError(f"Failed to delete sell order: {response.status_code} - {response.text}")
     
def get_orders_by_attr(username: str, attr: str="id") -> dict[str, list[MarketOrder]]:
    '''
    Fetches all active sell orders made by a specific user on Warframe Market.
    Returns a list of dictionaries with item name, price, and mod rank (if available).
    '''
    url = f"{BASE_URL}/profile/{username}/orders"
    response = requests.get(url)

    if response.status_code != 200:
        raise ValueError(f"Failed to fetch orders: {response.status_code} - {response.text}")

    data = response.json()
    orders = data.get("payload", {}).get("sell_orders", [])

    sell_orders = {}
    
    for order in orders:
        market_order = MarketOrder(
            order["id"],
            order["item"]["id"],
            order["item"]["en"]["item_name"],
            order["item"]["url_name"],
            order["platinum"],
            order.get("mod_rank", None),  # Only mods and arcanes have mod_rank
            order["quantity"]
        )
        if sell_orders.get(getattr(market_order, attr)):
            sell_orders[getattr(market_order, attr)].append(market_order)
        else:
            sell_orders[getattr(market_order, attr)] = [market_order]

    return sell_orders

def run_deleter(token: str, username: str):
    '''
    Deletes all active sell orders from the authorized user.
    '''
    sell_orders = get_orders_by_attr(username)

    if not sell_orders:
        print("[!] No active sell orders to delete.")
        return

    print(f"[+] Found {len(sell_orders)} sell orders. Deleting...")

    for order_id in sell_orders:
        delete_sell_order(token, order_id)

    print("[+] All sell orders deleted successfully!")
    
def create_line(info: LineInfo) -> str:
    '''
    Creates a SELL_LIST_FILE line from a LineInfo struct
    '''
    line = ' ' * SELL_LIST_INDENT
    if info.quantity == 0:
        line += '  '
    else: 
        line += '+ '
    
    line += f'{info.item_name.replace("_", " ")}'
    if info.rank != None:
        line += f' r{info.rank}'
    if info.min_price != None:
        line += f' min{info.min_price}'
    
    if info.quantity == 0:
        line += ' [OUT OF STOCK]'
    elif info.quantity != None:
        line += f' {info.quantity}'
    line += '\n'
    return line
    
   
def run_syncer(username: str):
    '''
    Syncs the SELL_LIST_FILE with the latest profile data from warframe.market
    '''
    market_orders = get_orders_by_attr(username, "item_name")
    if not market_orders:
        print("[!] No active sell orders to sync.")
        return
    ct = 0
    [[(ct := ct + 1) for i in j] for j in market_orders.values()]
    print(f"[+] Found {ct} sell orders. Syncing...")
    newfile = ""
    with open(SELL_LIST_FILE, "r") as file:
        with open((baklist := SELL_LIST_FILE.rsplit('.', 1))[0] + '_bak' + '.' + baklist[1], 'w') as bakfile:
            for line in file:
                bakfile.write(line)
                info = parse_line(line)
                if not info:
                    newfile += line
                    continue
                
                orders_list = market_orders.get(info.item_name, [])
                order = None
                for i in range(len(orders_list)):
                    if orders_list[i].rank == info.rank:
                        order = orders_list[i]
                        break
                    
                if not order:
                    info.quantity = 0
                else:
                    info.quantity = order.quantity
                    del market_orders[info.item_name][i]
                    if not market_orders[info.item_name]: del market_orders[info.item_name]
                    
                newfile += create_line(info)
    if market_orders:
        newfile += "\n- NEW ORDERS:\n"
    for order_list in market_orders.values():
        for market_order in order_list:
            newfile += create_line(LineInfo(market_order.item_name, market_order.rank, None, market_order.quantity))
                
    with open(SELL_LIST_FILE, 'w') as file:
        file.write(newfile)
    print("[+] All sell orders synced successfully!")
        
if __name__ == "__main__":
    # User credentials
    try:
        with open(CREDENTIAL_FILE, 'r') as file:
            data = json.load(file)
            email = data['email']
            password = data['password']
            username = data['username']
            csrf = data['csrf']
            cookie = data['cookie']
    except FileNotFoundError:
        print("Error: The file 'data.json' was not found.")
    except json.JSONDecodeError:
        print("Error: Invalid JSON format in 'data.json'.")
        
    try:
        # Authenticate and retrieve session token
        session_token = login(email, password, csrf, cookie)
    except ValueError as e:
        print(f"[!] Error: {e}")
        
    
    if len(sys.argv) == 1:
        run_seller(session_token, username)
    elif len(sys.argv) == 2 and (sys.argv[1] == '-s' or sys.argv[1] == '--sync'):
        run_syncer(username)
    elif len(sys.argv) == 2 and (sys.argv[1] == '-d' or sys.argv[1] == '--delete'):
        run_deleter(session_token, username)