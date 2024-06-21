from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import mysql.connector
from flask_compress import Compress
from controller.authentication import login, register, authentication_check, farmer_check, buyer_check, agent_check
from controller.produce import product_detail
from controller.cart import cart_data, delete_item, update_item, add_item, cart_items
from controller.checkout import checkout_page, checkout_func
from controller.orderhistory import order_history
from controller.delivery import get_status, set_status
from controller.producehistory import get_history
from controller.profile import get_profile, set_profile, get_update_page, set_pass
from controller.addproduce import get_produce_page, set_produce
from controller.category import category_page
from utilities import get_perm_address, get_buyer_address, category_items, get_categories, get_latest_items, sendSMS, get_agencies, show_produce, add_produce_sms, show_agencies, hash_password, check_password
from db_connection import connect, get_db_connection
from web3 import Web3
from web3.exceptions import ContractLogicError
import json

w3 = Web3(Web3.HTTPProvider('http://127.0.0.1:7545'))
with open('build/contracts/Wallet.json') as f:
    contract_json = json.load(f)
    contract_abi = contract_json['abi']
app = Flask(__name__)
Compress(app)

app.config['SECRET_KEY'] = 'super secret key'
app.config['UPLOAD_FOLDER'] = '/static/user_profile_images'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024
app.config['ENV'] = 'development'

# Smart contract ABI and address
contract_address = '0x22d5751e5c473E4b69Ab47784A1D8a4FAe5e27E1'
contract = w3.eth.contract(address=contract_address, abi=contract_abi)

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    # Check if user already exists in local database
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
    user = cursor.fetchone()
    if user:
        return jsonify({'error': 'User already exists in the local database'}), 400

    # Check if user already exists in the blockchain
    user_exists = contract.functions.userExists(username).call()
    if user_exists:
        return jsonify({'error': 'User already exists in the blockchain'}), 400

    try:
        # Register user in the blockchain
        tx_hash = contract.functions.register(username, password).transact({'from': w3.eth.accounts[0]})
        w3.eth.wait_for_transaction_receipt(tx_hash)

        # Register user in the local database
        hashed_password = hash_password(password).decode('utf-8')
        cursor.execute("INSERT INTO users (username, password) VALUES (%s, %s)", (username, hashed_password))
        conn.commit()

        return jsonify({'message': 'User registered successfully on blockchain and database'}), 201

    except Exception as e:
        return jsonify({'error': str(e)}), 500

    finally:
        cursor.close()
        conn.close()

@app.route('/deposit', methods=['POST'])
def deposit():
    data = request.get_json()
    amount = data.get('amount')

    try:
        # Interact with smart contract
        tx_hash = contract.functions.depositFunds().transact({'from': w3.eth.accounts[0], 'value': Web3.to_wei(amount, 'ether')})
        w3.eth.wait_for_transaction_receipt(tx_hash)

        return jsonify({'message': 'Funds deposited successfully'}), 200
    except ContractLogicError as e:
        return jsonify({'error': f'An error occurred during deposit: {str(e)}'}), 500
    except Exception as e:
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500


@app.route('/transfer', methods=['POST'])
def transfer():
    data = request.get_json()
    username = data.get('username')
    to_address = data.get('to_address')
    amount = float(data.get('amount'))
    password = data.get('password')

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT password FROM users WHERE username = %s", (username,))
    result = cursor.fetchone()
    cursor.close()
    conn.close()

    if result and check_password(password, result[0]):
        try:
            # Check if the account has enough balance
            sender_balance = w3.eth.get_balance(w3.eth.accounts[0])
            transfer_amount = w3.to_wei(amount, 'ether')
            gas_estimate = contract.functions.transferFunds(to_address, transfer_amount, password).estimate_gas({'from': w3.eth.accounts[0]})

            # Ensure the account has enough balance for the transfer amount plus gas fees
            if sender_balance < transfer_amount + gas_estimate * w3.eth.gas_price:
                return jsonify({'error': 'Insufficient balance for transfer including gas fees'}), 400

            # Interact with smart contract
            tx_hash = contract.functions.transferFunds(to_address, transfer_amount, password).transact({'from': w3.eth.accounts[0]})
            w3.eth.wait_for_transaction_receipt(tx_hash)
            return jsonify({'message': 'Funds transferred successfully'}), 200
        except ContractLogicError as e:
            return jsonify({'error': f'An error occurred during transfer: {str(e)}'}), 500
    else:
        return jsonify({'message': 'Invalid credentials'}), 401


@app.before_request
def before_request():
    if not request.is_secure and app.config["ENV"] != "development":
        url = request.url.replace("http://", "https://", 1)
        code = 301
        return redirect(url, code)

@app.route('/', methods=['GET', 'POST'])
def main():
    return redirect(url_for('index'))

@app.route('/index', methods=['GET', 'POST'])
def index():
    categories = get_categories()
    latest = get_latest_items()
    cat_items = [category_items(category[0]) for category in categories]
    if session.get('email', False):
        if session['role'] == "Farmer":
            return redirect(url_for('producehistory'))
        if session['role'] == "Delivery Agent":
            return redirect(url_for('delivery'))
        items, subtotal, items_len = cart_items()
        return render_template('index-2.html', items=items, subtotal=subtotal, category_items=cat_items, categories=categories, latest=latest)
    return render_template('index-2.html', categories=categories, category_items=cat_items, latest=latest)

@app.route('/category/<category>')
def category(category):
    return category_page(category)

@app.route('/about-us')
def about():
    items, subtotal, items_len = cart_items() if session.get('email', False) else ([], 0, 0)
    return render_template('about-us.html', items=items, subtotal=subtotal, items_len=items_len)

@app.route('/contact-us')
def contact():
    items, subtotal, items_len = cart_items() if session.get('email', False) else ([], 0, 0)
    return render_template('contact.html', items=items, subtotal=subtotal, items_len=items_len)

@app.route('/cart')
@authentication_check
@buyer_check
def cart():
    items, latestitems, categories, subtotal, items_len = cart_data()
    return render_template('cart.html', items=items, latestitems=latestitems, categories=categories, subtotal=subtotal, number=items_len)

@app.route('/cart_item', methods=['POST'])
@authentication_check
@buyer_check
def item():
    if request.form.get('type', None) == 'delete':
        delete_item(request.form.get('item_id'))
        return redirect(request.referrer)
    elif request.form.get('type', None) == 'update':
        msg = update_item(request.form.get('item_id', None), request.form.get('quantity', None), request.form.get('produce_id', None))
        flash(msg)
        return redirect(request.referrer)
    elif request.form.get('type', None) == 'add':
        add_item(request.form.get('produce_id', None), request.form.get('quantity', None))
        return redirect(request.referrer)

@app.route('/product/<produce_id>', methods=['GET', 'POST'])
def product(produce_id):
    return product_detail(produce_id)

@app.route('/checkout', methods=['GET', 'POST'])
@authentication_check
@buyer_check
def checkout():
    if request.method == 'GET':
        return checkout_page()
    if request.method == 'POST':
        return checkout_func()

@app.route('/history')
@authentication_check
@buyer_check
def history():
    items, subtotal, items_len = cart_items()
    perm_address = get_perm_address()
    buyer_address = get_buyer_address()
    purchased_items = order_history()
    return render_template('orderhistory.html', items=items, subtotal=subtotal, items_len=items_len, purchased_items=purchased_items, perm_address=perm_address, buyer_address=buyer_address)

@app.route('/delivery', methods=['GET', 'POST'])
@authentication_check
@agent_check
def delivery():
    if request.method == 'GET':
        return get_status()
    if request.method == 'POST':
        return set_status(request.form.get('order_id', None), request.form.get('delivery_status', None))

@app.route('/produce-history')
@authentication_check
@farmer_check
def producehistory():
    return get_history()

@app.route('/profile', methods=['GET', 'POST'])
@authentication_check
def profile():
    if request.method == 'GET':
        return get_profile()
    if request.method == 'POST':
        return set_profile()

@app.route('/add-produce', methods=['GET', 'POST'])
@authentication_check
@farmer_check
def add_produce():
    if request.method == 'GET':
        return get_produce_page()
    if request.method == 'POST':
        return set_produce()

@app.route('/update-password', methods=['GET', 'POST'])
@authentication_check
def updatepassword():
    if request.method == 'GET':
        return get_update_page()
    if request.method == 'POST':
        return set_pass(app)

@app.route('/login', methods=['GET', 'POST'])
def auth():
    if request.method == 'GET':
        return render_template('login.html')
    if request.method == 'POST':
        return login(app)

@app.route('/register', methods=['GET', 'POST'])
def registration():
    if request.method == 'GET':
        return render_template('register.html')
    if request.method == 'POST':
        return register(app)

@app.route('/logout', methods=['GET'])
def logout():
    session.pop('email', None)
    session.pop('role', None)
    session.pop('id', None)
    session.pop('url', None)
    return redirect(url_for('index'))

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(403)
def page_not_found(e):
    return render_template('403.html'), 403

@app.route('/sms', methods=['POST'])
def sms():
    print(request.form)
    body = request.form
    content = body['content']
    sender = body['sender'][2:]

    cnt = content.split('\n')
    print(cnt)

    if cnt[1].lower() == 'help':
        s = "1) ADD\n"

        s += "Format your message as given below:\n"

        s += "ADD\n<Name>\n<Price>\n<Quantity>\n<Category>\
            [Fruits, Vegetables, Spices, Pulses, Grains]\
            \n<Description>\
            \n<Delivery Agency>(Obtained from HELP)\
            \n\n"

        s += "2) SHOW LATEST PRODUCE\n\n"

        s += "3) DELIVERY AGENCIES"
        sendSMS(sender, s)
        print(s)

    if cnt[1].lower() == 'add':
        if len(cnt[2:]) == 6:
            query = "SELECT user_id FROM user WHERE user_phone = %s"
            try:
                connection = connect()
                cur = connection.cursor()
                params = (sender,)
                cur.execute(query, params)
                farmer_id = cur.fetchone()
                farmer_id = farmer_id[0]
                print(farmer_id)
                ret = add_produce_sms(cnt[2:], farmer_id)
                print(ret)
                if ret:
                    sendSMS(sender, "Produce added successfully")
                    print("yes")
                else:
                    print("no")
            except mysql.connector.Error as err:
                print(err)
            finally:
                cur.close()
                connection.close()

    if cnt[1].lower().replace(" ", "") == 'showlatestproduce':
        query = "SELECT user_id FROM user WHERE user_phone = %s"
        try:
            connection = connect()
            cur = connection.cursor()
            params = (sender,)
            cur.execute(query, params)
            farmer_id = cur.fetchone()
            farmer_id = farmer_id[0]
            print(farmer_id)
            s = show_produce(farmer_id)
            sendSMS(sender, s)
            print(s)
        except mysql.connector.Error as err:
            print(err)
        finally:
            cur.close()
            connection.close()

    if cnt[1].lower().replace(" ", "") == 'deliveryagencies':
        query = "SELECT user_id FROM user WHERE user_phone = %s"
        try:
            connection = connect()
            cur = connection.cursor()
            params = (sender,)
            cur.execute(query, params)
            farmer_id = cur.fetchone()
            farmer_id = farmer_id[0]
            print(farmer_id)
            s = show_agencies()
            sendSMS(sender, s)
            print(s)
        except mysql.connector.Error as err:
            print(err)
        finally:
            cur.close()
            connection.close()
    return "1"

@app.route('/service-worker.js')
def sw():
    return app.send_static_file('service-worker.js')


if __name__ == '__main__':
    app.config['SECRET_KEY'] = 'super secret key'
    app.config['UPLOAD_FOLDER'] = '/static/user_profile_images'
    app.config['MAX_CONTENT_LENGTH'] = 100 * 1024
    app.config['ENV'] = 'development'
    app.run('0.0.0.0', port=5000, debug=True)
