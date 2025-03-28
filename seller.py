import requests

BASE_URL = "https://api.warframe.market/v1"
CREDENTIAL_FILE = "credentials.txt"
COOKIE_FILE = "cookie.txt"
SELL_LIST_FILE = "sell_list.txt"
DEFAULT_MIN_PRICE = 9

def login(username: str, password: str, csrf: str, cookie:str) -> str:
    '''Logs in to Warframe Market and returns a session token'''
    # csrf_token = get_csrf_token()
    url = f"{BASE_URL}/auth/signin"
    payload = {"auth_type": "cookie", "email": username, "password": password}
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
    '''Retrieves the item ID for the given item name'''
    url = f"{BASE_URL}/items/{item_name}"
    response = requests.get(url)

    if response.status_code == 200:
        data = response.json()
        return data["payload"]["item"]["id"]
    else:
        raise ValueError(f"Failed to get item ID: {response.status_code} - {response.text}")
    
def get_price(item_name: str, min_price: int) -> int:
    '''Gets the lowest sell order platinum price for an item from a user who is online-in-game.'''
    
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

def create_sell_order(token: str, item_id: str, platinum: int, quantity: int, rank: int) -> None:
    '''Creates a sell order for the given item.'''
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

    response = requests.post(url, json=order_payload, headers=headers)

    if response.status_code == 200:
        print("[+] Sell order created successfully!")
    else:
        raise ValueError(f"Failed to create sell order: {response.status_code} - {response.text}")

def run():
    # User credentials
    with open(COOKIE_FILE, "r") as file:
        cookie = file.readline().strip()
    with open(CREDENTIAL_FILE, "r") as file:
        creds = [line.strip() for line in file.readlines()]
    username = creds[0]
    password = creds[1]
    csrf = creds[2]
    
    try:
        # Authenticate and retrieve session token
        session_token = login(username, password, csrf, cookie)

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
                    create_sell_order(session_token, item_id, plat_price, quantity, rank)

    except ValueError as e:
        print(f"[!] Error: {e}")
        
        
if __name__ == "__main__":
    run()