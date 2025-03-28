import requests
import sys
import json

BASE_URL = "https://api.warframe.market/v1"
CREDENTIAL_FILE = "credentials.json"
SELL_LIST_FILE = "sell_list.txt"
DEFAULT_MIN_PRICE = 9

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
        raise ValueError(f"Failed to get item ID: {response.status_code} - {response.text}")
    
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
        if price != lowest_price: print (f"    [!] Under minimum price of {min_price}")
        print(f"    [i] Selling for {price} platinum")
        
        return price
    else:
        raise ValueError(f"No in-game sell orders found for {item_name}")

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
        print("[+] Sell order created successfully!")
    else:
        print("[!] Error: order already exists.")
        orders_by_item_id = get_user_sell_orders_by_attr(username, "item_id")
        print(f"    [+] Got sell orders for user: {username}")
        print("    Attempting to update order...")
        response = requests.put(f"{url}/{orders_by_item_id[item_id]['id']}", headers=headers, json=update_payload)
        if response.status_code == 200:
            print("    [+] Sell order updated successfully!")
        else:
            print(f"    [!] Update failed: {response.status_code} - {response.text}")
        

def run_seller(token: str, username: str):
    '''
    Creates sell orders with items and specificiations listed in the SELL_LIST_FILE
    '''
    
    with open(SELL_LIST_FILE, "r") as file:
        for line in file:
            line = line.strip()
            if line.startswith("+"):
                line = line[1:].strip()
                quantity = None
                rank = None
                min_price = None
                
                
                # Get item quantity, rank and min price
                linelist = line.split()
                for item in reversed(linelist):
                    if item.isdigit():
                        quantity = int(item)
                    elif item.startswith("r") and item[1:].isdigit():
                        rank = int(item[1:])
                    elif item.startswith("min") and item[3:].isdigit():
                        min_price = int(item[3:])
                        
                if quantity != None:
                    del linelist[-1]
                else:
                    quantity = 1 # Default quantity
                
                if rank != None:
                    del linelist[-1]
                    
                if min_price != None:
                    del linelist[-1]
                else:
                    min_price = DEFAULT_MIN_PRICE
                
                line = "_".join(linelist)
                
                # Get item name
                item_name = line.strip().replace(" ", "_")
                item_id = get_item_id(item_name)
                
                # Get the lowest reasonable in-game sell order price and create the sell order
                plat_price = get_price(item_name, min_price)
                create_sell_order(token, item_id, plat_price, quantity, rank, username)
        
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
     
def get_user_sell_orders_by_attr(username: str, attr: str="id"):
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
        format = {
            "id": order["id"],
            "item_name": order["item"]["en"]["item_name"],
            "item_id": order["item"]["id"],
            "platinum": order["platinum"],
            "mod_rank": order.get("mod_rank", None)  # Only mods and arcanes have mod_rank
        }
        sell_orders[format[attr]] = format

    return sell_orders

def run_deleter(token: str, username: str):
    '''
    Deletes all active sell orders from the authorized user.
    '''
    sell_orders = get_user_sell_orders_by_attr(username)

    if not sell_orders:
        print("[!] No active sell orders to delete.")
        return

    print(f"[+] Found {len(sell_orders)} sell orders. Deleting...")

    for order_id in sell_orders:
        delete_sell_order(token, order_id)

    print("[+] All sell orders deleted successfully!")
   
def run_updater(username: str):
    '''
    Updates the SELL_LIST_FILE with the latest profile data from warframe.market
    '''
    print(get_user_sell_orders_by_attr(username))
    
        
        
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
        
    
    if len(sys.argv) == 1 or ((len(sys.argv)) == 2 and (sys.argv[1] == '-s' or sys.argv[1] == '--sell')):
        run_seller(session_token, username)
    elif len(sys.argv) == 2 and (sys.argv[1] == '-u' or sys.argv[1] == '--update'):
        run_updater(username)
    elif len(sys.argv) == 2 and (sys.argv[1] == '-d' or sys.argv[1] == '--delete'):
        run_deleter(session_token, username)