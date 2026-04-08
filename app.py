import os
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, jsonify, request, render_template, session, redirect, url_for
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import pymongo
from datetime import datetime, timedelta
from bson.objectid import ObjectId
import cloudinary
import cloudinary.uploader
import cloudinary.api
import math
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
import requests
from concurrent.futures import ThreadPoolExecutor
from PIL import Image, ImageOps
import io
from flask_apscheduler import APScheduler
from datetime import datetime, timedelta
import uuid

scheduler = APScheduler()

GITHUB_CLIENT_ID = 'Ov23liVkvOCL4Wr5JCVg'
GITHUB_CLIENT_SECRET = '81d0508b3dd05a03ea6b94f688059243385d69d1'

DISCORD_CLIENT_ID = '1490490277519954021'
DISCORD_CLIENT_SECRET = 'MLmGelVhI2nmdo6WMyED32MYGHegyujZ'
DISCORD_REDIRECT_URI = 'http://localhost:5000/discord-callback'


app = Flask(__name__)
app.secret_key = 'super_secret_key_123'


cloudinary.config(
    cloud_name='dkpjcosmx',
    api_key='592254249338645',
    api_secret='E67gLsV_rrDFtDy9yUL_fXD5rbQ'
)

EMAIL_SENDER = 'cryptomarketplace.app@gmail.com'
EMAIL_PASSWORD = 'mecq vuvz hftf atyj'

UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

TOTAL_SUPPLY = 100000000
ALLOCATION_FOR_GIFTS = 10000000
SIGNUP_BONUS = 100

client = pymongo.MongoClient("mongodb://localhost:27017/")
db = client["CryptoMarketplace"]
products_col = db["products"]
users_col = db["users"]
chats_col = db["chats"]
try:
    users_col.create_index("username", unique=True)
    users_col.create_index("email", unique=True)
except Exception as e:
    print(f"Index creation warning (ignore if duplicates exist): {e}")

orders_col = db["orders"]

PLATFORM_WALLETS = {
    "BTC": {"address": "17e1JLisfjAp2UAVzYnBfwtwSgCo4MpTTk", "network": "BTC"},
    "ETH": {"address": "0x983dcbbabe416683e78c1352b344621a139c1b07", "network": "ERC20"},
    "SOL": {"address": "4fFLBwHauEU2cMdzuaqgRAzcGoKPU75ZpAdWx9CeFWQc", "network": "Solana"},
    "USDT": {"address": "TT9F9As3Lj1sUptcLmWGd8vSaeBqCdPqyV", "network": "TRC20"}
}
FEE_PERCENT = 0.01
TRACKING_DEADLINE_DAYS = 3

def calculate_distance(lat1, lon1, lat2, lon2):
    try:
        R = 6371.0
        lat1, lon1, lat2, lon2 = map(math.radians, [float(lat1), float(lon1), float(lat2), float(lon2)])
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = math.sin(dlat / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c
    except:
        return 999999.0


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def delete_image_from_cloudinary(image_url):
    if not image_url: return
    try:
        public_id = image_url.split('/')[-1].split('.')[0]
        cloudinary.uploader.destroy(public_id)
        print(f"Deleted from Cloudinary: {public_id}")
    except Exception as e:
        print(f"Error deleting image: {e}")


def send_email_code(to_email, code):
    try:
        msg = MIMEMultipart()
        msg['From'] = f"Crypto Marketplace Team <{EMAIL_SENDER}>"
        msg['To'] = to_email
        msg['Subject'] = "Crypto Marketplace - Verification Code"

        body = f"Welcome to Crypto Marketplace!\n\nYour verification code is: {code}\n\nEnter this code on the website to activate your account."
        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        text = msg.as_string()
        server.sendmail(EMAIL_SENDER, to_email, text)
        server.quit()
        print("Email sent successfully")
        return True
    except Exception:
        # Safe print to prevent Windows console crash
        print("Failed to send email. Check credentials or connection.")
        return False

@app.route('/')
def home():
    user_info = session.get('username')
    return render_template('index.html', user=user_info)


@app.route('/login-page')
def login_page():
    return render_template('login.html')


@app.route('/verify-page')
def verify_page():
    return render_template('verify.html')


@app.route('/product/<product_id>')
def product_page(product_id):
    try:
        product = products_col.find_one({"_id": ObjectId(product_id)})
    except:
        return "Product ID invalid", 404

    if not product:
        return "Product not found", 404

    is_favorite = False

    if 'username' in session:
        cat = product.get('category')
        if cat:
            users_col.update_one(
                {"username": session['username']},
                {"$inc": {f"preferences.{cat}": 1}}
            )

        user_data = users_col.find_one({"username": session['username']})
        if user_data and product_id in user_data.get('favorites', []):
            is_favorite = True

    product['_id'] = str(product['_id'])

    seller = users_col.find_one({"_id": ObjectId(product.get('seller_id'))}) if product.get('seller_id') else None
    seller_data = {
        "username": seller['username'] if seller else "Unknown",
        "avatar": seller.get('avatar') if seller else "",
        "rating": seller.get('avg_rating', 0) if seller else 0,
        "joined": seller.get('created_at').strftime('%Y') if seller and seller.get('created_at') else "2025"
    }

    return render_template('products.html', product=product, seller=seller_data, user=session.get('username'),
                           is_favorite=is_favorite)


@app.route('/inbox')
def inbox():
    if 'username' not in session:
        return redirect('/login-page')

    my_id = session['user_id']
    my_name = session['username']

    user_chats_cursor = chats_col.find({"participants": my_id})

    my_chats = []
    for chat in user_chats_cursor:
        other_name = "Unknown"
        if 'participants_names' in chat:
            names = chat['participants_names']
            if len(names) >= 2:
                if names[0] == my_name:
                    other_name = names[1]
                else:
                    other_name = names[0]

        last_msg = "No messages yet"
        if chat.get('messages') and len(chat['messages']) > 0:
            last_msg = chat['messages'][-1]['content']

        my_chats.append({
            "id": str(chat['_id']),
            "product_title": chat.get('product_title', 'Unknown Item'),
            "other_name": other_name,
            "last_message": last_msg
        })

    return render_template('inbox.html', chats=my_chats, user=my_name)


@app.route('/chat-page/<chat_id>')
def chat_page(chat_id):
    if 'username' not in session: return redirect('/login-page')

    chat = chats_col.find_one({"_id": ObjectId(chat_id)})
    other_user_id = None
    if chat:
        for p_id in chat['participants']:
            if p_id != session['user_id']:
                other_user_id = p_id
                break

    return render_template('chat.html', chat_id=chat_id, user=session['username'], seller_id=other_user_id)


@app.route('/register', methods=['POST'])
def register():
    try:
        data = request.json
        if users_col.find_one({"username": data['username']}):
            return jsonify({"error": "Username taken"}), 400

        hashed_password = generate_password_hash(data['password'])
        code = str(random.randint(100000, 999999))

        if data.get('email'):
            send_email_code(data['email'], code)

        pipeline = [{"$group": {"_id": None, "total": {"$sum": "$wallet_balance"}}}]
        res = list(users_col.aggregate(pipeline))
        total_distributed = res[0]['total'] if res else 0

        bonus = 0
        bonus_expiry = None

        if total_distributed + SIGNUP_BONUS <= ALLOCATION_FOR_GIFTS:
            bonus = SIGNUP_BONUS
            bonus_expiry = datetime.now() + timedelta(weeks=2)

        new_user = {
            "username": data['username'],
            "password": hashed_password,
            "email": data.get('email', ''),
            "created_at": datetime.now(),
            "is_verified": False,
            "verification_code": code,
            "avatar": None,
            "avg_rating": 0,
            "reviews": [],
            "wallet_balance": bonus,
            "bonus_expires_at": bonus_expiry
        }
        users_col.insert_one(new_user)

        return jsonify({"message": "Welcome! 100 FREE COINS added"}), 201
    except Exception:
        # Safe catch to prevent server crash during registration
        print("Error occurred during registration")
        return jsonify({"error": "Internal server error"}), 500


@app.route('/get-balance')
def get_balance():
    if 'username' not in session:
        return jsonify({"balance": 0, "has_badge": False})

    user = users_col.find_one({"username": session['username']})
    if user:
        return jsonify({
            "balance": user.get('wallet_balance', 0),
            "has_badge": user.get('blue_badge', False)
        })
    return jsonify({"balance": 0, "has_badge": False})


@app.route('/verify-account', methods=['POST'])
def verify_account():
    data = request.json
    username = data.get('username')
    code = data.get('code')

    user = users_col.find_one({"username": username})

    if not user:
        return jsonify({"error": "User not found"}), 404

    if user.get('verification_code') == code:
        users_col.update_one(
            {"username": username},
            {"$set": {"is_verified": True}, "$unset": {"verification_code": ""}}
        )

        session['username'] = user['username']
        session['user_id'] = str(user['_id'])

        return jsonify({"message": "Verified!"}), 200
    else:
        return jsonify({"error": "Wrong code"}), 400


def check_bonus_expiry(user_id):
    user = users_col.find_one({"_id": ObjectId(user_id)})
    if not user: return

    if user.get('bonus_expires_at') and user.get('wallet_balance') > 0:
        if datetime.now() > user['bonus_expires_at']:
            users_col.update_one(
                {"_id": ObjectId(user_id)},
                {"$set": {"wallet_balance": 0}, "$unset": {"bonus_expires_at": ""}}
            )
            print(f"Expired bonus for user {user['username']}")


@app.route('/login', methods=['POST'])
def login():
    data = request.json
    user = users_col.find_one({"username": data['username']})

    if user:
        password_correct = False
        try:
            if check_password_hash(user['password'], data['password']):
                password_correct = True
        except:
            if user['password'] == data['password']:
                password_correct = True

        if password_correct:
            if not user.get('is_verified', True):
                return jsonify({"error": "Account not verified", "need_verify": True}), 403

            check_bonus_expiry(user['_id'])

            session['username'] = user['username']
            session['user_id'] = str(user['_id'])
            return jsonify({"message": "Login successful!"}), 200

    return jsonify({"error": "Invalid credentials"}), 401


GOOGLE_CLIENT_ID = "716094634129-is5abmoghh7aogil36vh8krnvjdeult7.apps.googleusercontent.com"
@app.route('/google-login', methods=['POST'])
def google_login():
    data = request.json
    token = data.get('credential')

    try:
        idinfo = id_token.verify_oauth2_token(token, google_requests.Request(), GOOGLE_CLIENT_ID)

        email = idinfo['email']
        name = idinfo.get('name', email.split('@')[0])
        google_id = idinfo['sub']
        picture = idinfo.get('picture')

        user = users_col.find_one({"email": email})

        if not user:
            new_user = {
                "username": name,
                "email": email,
                "password": "",
                "created_at": datetime.now(),
                "is_verified": True,
                "verification_code": "",
                "avatar": picture,
                "avg_rating": 0,
                "reviews": [],
                "wallet_balance": 100,
                "google_id": google_id
            }
            result = users_col.insert_one(new_user)
            session['username'] = new_user['username']
            session['user_id'] = str(result.inserted_id)
        else:
            session['username'] = user['username']
            session['user_id'] = str(user['_id'])

        return jsonify({"message": "Login successful"}), 200

    except ValueError:
        return jsonify({"error": "Invalid token"}), 401
    except Exception as e:
        print(f"Google login error: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')


@app.route('/products', methods=['GET'])
def get_products():
    query = request.args.get('q', '')
    category = request.args.get('category', 'All')
    country = request.args.get('country', 'All')

    user_lat = request.args.get('lat')
    user_lng = request.args.get('lng')
    radius = request.args.get('radius')

    search_filter = {"status": {"$ne": "sold"}}

    if query:
        text_search = {
            "$or": [
                {"title": {"$regex": query, "$options": "i"}},
                {"description": {"$regex": query, "$options": "i"}}
            ]
        }
        if "$or" in search_filter:
            search_filter = {"$and": [search_filter, text_search]}
        else:
            search_filter.update(text_search)

    if category and category != 'All':
        search_filter["category"] = category

    if country != 'All' and country != 'Global':
        search_filter["country"] = {"$in": [country, "Global"]}

    now = datetime.now()
    # Fetching by newest first initially
    products_cursor = products_col.find(search_filter).sort([("created_at", -1)])
    products_list = []

    for product in products_cursor:
        if product.get('is_promoted') and product.get('promotion_expiry'):
            if product['promotion_expiry'] < now:
                products_col.update_one({"_id": product['_id']}, {"$set": {"is_promoted": False}})
                product['is_promoted'] = False

        if user_lat and user_lng and radius and radius != '0':
            p_lat = product.get('lat')
            p_lng = product.get('lng')
            if p_lat and p_lng:
                dist = calculate_distance(user_lat, user_lng, p_lat, p_lng)
                if dist > float(radius):
                    continue
                product['distance'] = round(dist, 1)
            else:
                if country != 'Global':
                    continue

        product['_id'] = str(product['_id'])

        if 'seller_id' in product and product['seller_id']:
            s_id = str(product['seller_id'])
            product['seller_id'] = s_id
            try:
                seller = users_col.find_one({"_id": ObjectId(s_id)})
                product['seller_rating'] = seller.get('avg_rating', 0) if seller else 0
                product['seller_badge'] = seller.get('blue_badge', False) if seller else False
            except:
                product['seller_rating'] = 0
                product['seller_badge'] = False
        else:
            product['seller_rating'] = 0

        products_list.append(product)

    # --- SMART ALGORITHM: SORT BY USER PREFERENCES ---
    if 'username' in session and category == 'All' and not query:
        user = users_col.find_one({"username": session['username']})
        if user and 'preferences' in user:
            user_prefs = user['preferences']

            # Sort categories by highest click count
            sorted_prefs = sorted(user_prefs.items(), key=lambda item: item[1], reverse=True)
            top_categories = [k for k, v in sorted_prefs]

            def recommendation_score(p):
                score = 0
                if p.get('is_promoted'):
                    score += 10000  # Promoted always first

                cat = p.get('category')
                if cat in top_categories:
                    # Higher score for highly ranked categories
                    score += (len(top_categories) - top_categories.index(cat)) * 100

                return score

            # Python's sort is stable, it will keep 'created_at' order for items with the same score
            products_list.sort(key=recommendation_score, reverse=True)
    else:
        # Standard sort if not logged in or if searching/filtering: Promoted items first
        products_list.sort(key=lambda p: p.get('is_promoted', False), reverse=True)
    # -------------------------------------------------

    return jsonify(products_list)


@app.route('/add-product', methods=['POST'])
def add_product():
    if 'username' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    user = users_col.find_one({"_id": ObjectId(session['user_id'])})
    listing_type = request.form.get('listing_type', 'regular')
    product_currency = request.form.get('currency', 'BTC')

    if listing_type == 'escrow':
        user_wallets = user.get('payout_wallets', [])
        has_matching_wallet = any(w.get('currency') == product_currency for w in user_wallets)

        if not has_matching_wallet:
            return jsonify({
                "error": "wallet_missing",
                "message": f"You must configure a {product_currency} payout wallet in your profile before creating a Secure Escrow listing for this currency."
            }), 400

    image_urls = []

    if 'images' in request.files:
        files = request.files.getlist('images')
        file_data_list = []

        for file in files:
            if file and file.filename != '':
                file.seek(0)
                file_data_list.append((file.filename, file.read(), file.content_type))

        def upload_worker(file_info):
            fname, fdata, ftype = file_info
            try:
                img = Image.open(io.BytesIO(fdata))

                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")

                target_size = (800, 800)
                img = ImageOps.fit(img, target_size, Image.Resampling.LANCZOS)

                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format='JPEG', quality=85)
                img_byte_arr.seek(0)

                files_payload = {'fileToUpload': (fname, img_byte_arr.read(), 'image/jpeg')}
                data_payload = {'reqtype': 'fileupload'}
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }

                res = requests.post('https://catbox.moe/user/api.php', files=files_payload, data=data_payload, headers=headers)

                if res.status_code == 200 and res.text.startswith('http'):
                    return res.text.strip()
            except Exception as e:
                print(f"Image processing or upload error: {e}")
            return None

        with ThreadPoolExecutor(max_workers=5) as executor:
            results = executor.map(upload_worker, file_data_list)
            for res in results:
                if res:
                    image_urls.append(res)

    lat = request.form.get('lat', type=float)
    lng = request.form.get('lng', type=float)

    country = 'Global'
    if lat is not None and lng is not None:
        try:
            geo_url = f"https://api.bigdatacloud.net/data/reverse-geocode-client?latitude={lat}&longitude={lng}&localityLanguage=en"
            geo_res = requests.get(geo_url, timeout=3)
            if geo_res.status_code == 200:
                geo_data = geo_res.json()
                fetched_country = geo_data.get('countryName')
                if fetched_country:
                    if fetched_country == "United States of America":
                        country = "USA"
                    elif fetched_country == "United Kingdom":
                        country = "UK"
                    else:
                        country = fetched_country
        except Exception as e:
            print(f"Geocoding error: {e}")

    new_product = {
        "title": request.form.get('title'),
        "description": request.form.get('description'),
        "listing_type": request.form.get('listing_type', 'regular'),
        "price": float(request.form.get('price')),
        "currency": request.form.get('currency'),
        "category": request.form.get('category'),
        "country": country,
        "lat": lat,
        "lng": lng,
        "images": image_urls,
        "image": image_urls[0] if image_urls else '',
        "seller_name": session['username'],
        "seller_id": session['user_id'],
        "created_at": datetime.now(),
        "status": "available",
        "is_promoted": False
    }

    products_col.insert_one(new_product)
    return jsonify({"message": "Product added with auto-detected country!"}), 201


@app.route('/start-chat', methods=['POST'])
def start_chat():
    if 'username' not in session: return jsonify({"error": "Login required"}), 401

    data = request.json
    seller_id = data.get('seller_id')
    product_title = data.get('product_title')
    product_id = data.get('product_id')

    current_user_id = session['user_id']
    if seller_id == current_user_id: return jsonify({"error": "Cannot chat with yourself"}), 400

    existing_chat = chats_col.find_one({
        "participants": {"$all": [current_user_id, seller_id]},
        "product_title": product_title
    })
    if existing_chat: return jsonify({"chat_id": str(existing_chat['_id'])})

    new_chat = {
        "participants": [current_user_id, seller_id],
        "participants_names": [session['username'], data.get('seller_name')],
        "product_title": product_title,
        "product_id": product_id,
        "messages": [],
        "created_at": datetime.now()
    }
    result = chats_col.insert_one(new_chat)
    return jsonify({"chat_id": str(result.inserted_id)})


@app.route('/get-messages/<chat_id>', methods=['GET'])
def get_messages(chat_id):
    if 'username' not in session: return jsonify({"error": "Login required"}), 401

    chat = chats_col.find_one({"_id": ObjectId(chat_id)})
    if not chat: return jsonify({"error": "Chat not found"}), 404

    updated = False
    for msg in chat['messages']:
        if not msg.get('read') and msg['sender'] != session['username']:
            msg['read'] = True
            updated = True

    if updated:
        chats_col.update_one({"_id": ObjectId(chat_id)}, {"$set": {"messages": chat['messages']}})

    chat['_id'] = str(chat['_id'])
    return jsonify(chat)


@app.route('/send-message', methods=['POST'])
def send_message():
    data = request.json
    msg = {
        "sender": session['username'],
        "content": data['content'],
        "timestamp": datetime.now().strftime("%H:%M"),
        "read": False
    }
    chats_col.update_one({"_id": ObjectId(data['chat_id'])}, {"$push": {"messages": msg}})
    return jsonify({"message": "Sent"})


@app.route('/my-profile')
def my_profile():
    if 'username' not in session:
        return redirect('/login-page')

    user = users_col.find_one({"username": session['username']})

    my_products = list(products_col.find({"seller_id": session['user_id']}))

    for p in my_products:
        p['_id'] = str(p['_id'])

    return render_template('profile.html', user=user, products=my_products)


@app.route('/upload-avatar', methods=['POST'])
def upload_avatar():
    if 'username' not in session: return jsonify({"error": "Login required"}), 401

    if 'avatar' in request.files:
        file = request.files['avatar']
        if file:
            try:
                upload_result = cloudinary.uploader.upload(file)
                new_avatar_url = upload_result['secure_url']

                users_col.update_one(
                    {"_id": ObjectId(session['user_id'])},
                    {"$set": {"avatar": new_avatar_url}}
                )
                return jsonify({"message": "Avatar updated", "avatar_url": new_avatar_url})
            except Exception as e:
                print(f"Avatar upload error: {e}")
                return jsonify({"error": "Upload failed"}), 500

    return jsonify({"error": "Invalid file"}), 400


@app.route('/delete-product/<product_id>', methods=['POST'])
def delete_product(product_id):
    if 'username' not in session: return jsonify({"error": "Unauthorized"}), 401

    product = products_col.find_one({"_id": ObjectId(product_id), "seller_id": session['user_id']})

    if product:
        if 'images' in product:
            for img_url in product['images']:
                delete_image_from_cloudinary(img_url)
        elif 'image' in product and product['image'].startswith('http'):
            delete_image_from_cloudinary(product['image'])

        products_col.delete_one({"_id": ObjectId(product_id)})
        return jsonify({"message": "Product and images deleted"})

    return jsonify({"error": "Failed to delete"}), 400


@app.route('/update-status', methods=['POST'])
def update_status():
    if 'username' not in session: return jsonify({"error": "Unauthorized"}), 401

    data = request.json
    product_id = data.get('product_id')
    new_status = data.get('status')

    if new_status == 'sold':
        product = products_col.find_one({"_id": ObjectId(product_id), "seller_id": session['user_id']})
        if product:
            if 'images' in product:
                for img_url in product['images']:
                    delete_image_from_cloudinary(img_url)
            elif 'image' in product and product['image'].startswith('http'):
                delete_image_from_cloudinary(product['image'])

            products_col.update_one(
                {"_id": ObjectId(product_id)},
                {"$set": {"status": "sold", "images": [], "image": ""}}
            )
            return jsonify({"message": "Marked as sold & images deleted"})

    products_col.update_one(
        {"_id": ObjectId(product_id), "seller_id": session['user_id']},
        {"$set": {"status": new_status}}
    )

    return jsonify({"message": "Status updated"})


@app.route('/add-review', methods=['POST'])
def add_review():
    if 'username' not in session: return jsonify({"error": "Login required"}), 401

    data = request.json
    seller_id = data.get('seller_id')
    rating = int(data.get('rating'))
    comment = data.get('comment', '')

    if seller_id == session['user_id']:
        return jsonify({"error": "You cannot rate yourself"}), 400

    review = {
        "reviewer": session['username'],
        "rating": rating,
        "comment": comment,
        "date": datetime.now()
    }

    users_col.update_one(
        {"_id": ObjectId(seller_id)},
        {"$push": {"reviews": review}}
    )

    seller = users_col.find_one({"_id": ObjectId(seller_id)})
    reviews = seller.get('reviews', [])
    if reviews:
        avg_rating = sum(r['rating'] for r in reviews) / len(reviews)
        users_col.update_one(
            {"_id": ObjectId(seller_id)},
            {"$set": {"avg_rating": round(avg_rating, 1)}}
        )

    return jsonify({"message": "Review added!"})


@app.route('/unread-count')
def unread_count():
    if 'username' not in session: return jsonify({"count": 0})

    my_username = session['username']
    count = 0

    user_chats = chats_col.find({"participants": session['user_id']})

    for chat in user_chats:
        for msg in chat.get('messages', []):
            if not msg.get('read') and msg.get('sender') != my_username:
                count += 1

    return jsonify({"count": count})


@app.route('/promote-product', methods=['POST'])
def promote_product():
    if 'username' not in session: return jsonify({"error": "Login required"}), 401

    data = request.json
    product_id = data.get('product_id')
    days = int(data.get('days'))
    payment_method = data.get('payment_method')

    price_per_day = 1 if days >= 7 else 2
    total_price = price_per_day * days

    if payment_method == 'FREE_COIN':
        total_price = total_price * 0.85

    print(f"Processing payment: ${total_price} via {payment_method} for {days} days.")

    expiry_date = datetime.now() + timedelta(days=days)

    products_col.update_one(
        {"_id": ObjectId(product_id), "seller_id": session['user_id']},
        {"$set": {
            "is_promoted": True,
            "promotion_expiry": expiry_date,
            "promotion_plan": f"{days} Days ({payment_method})"
        }}
    )

    return jsonify({"message": "Product Promoted Successfully!", "new_expiry": expiry_date.strftime("%d/%m/%Y")})


@app.route('/confirm-sale', methods=['POST'])
def confirm_sale():
    if 'username' not in session: return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    product_id = data.get('product_id')
    buyer_id = data.get('buyer_id')

    product = products_col.find_one({"_id": ObjectId(product_id), "seller_id": session['user_id']})
    if product:
        if 'images' in product:
            for url in product['images']: delete_image_from_cloudinary(url)
        elif 'image' in product:
            delete_image_from_cloudinary(product['image'])

    products_col.update_one(
        {"_id": ObjectId(product_id), "seller_id": session['user_id']},
        {"$set": {"status": "sold", "buyer_id": buyer_id, "images": [], "image": ""}}
    )
    return jsonify({"message": "Sale confirmed & images deleted!"})


@app.route('/user/<username>')
def public_profile(username):
    user = users_col.find_one({"username": username})
    if not user: return "User not found", 404

    user_products = list(products_col.find({"seller_name": username, "status": {"$ne": "deleted"}}))
    for p in user_products: p['_id'] = str(p['_id'])

    return render_template('public_profile.html', profile_user=user, products=user_products,
                           current_user=session.get('username'))

@app.route('/buy-blue-badge', methods=['POST'])
def buy_blue_badge():
    if 'username' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    user = users_col.find_one({"username": session['username']})
    if not user:
        return jsonify({"error": "User not found"}), 404

    if user.get('blue_badge'):
        return jsonify({"error": "You already have a blue badge!"}), 400

    if user.get('wallet_balance', 0) < 50:
        return jsonify({"error": "Not enough coins. Badge costs 50 coins."}), 400

    users_col.update_one(
        {"_id": user['_id']},
        {
            "$set": {"blue_badge": True},
            "$inc": {"wallet_balance": -50}
        }
    )
    return jsonify({"message": "Success! You are now a verified seller."}), 200


@app.route('/toggle-favorite/<product_id>', methods=['POST'])
def toggle_favorite(product_id):
    if 'username' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    user = users_col.find_one({"username": session['username']})
    favorites = user.get('favorites', [])

    if product_id in favorites:
        users_col.update_one({"username": session['username']}, {"$pull": {"favorites": product_id}})
        return jsonify({"status": "removed"}), 200
    else:
        users_col.update_one({"username": session['username']}, {"$addToSet": {"favorites": product_id}})
        return jsonify({"status": "added"}), 200


@app.route('/get-favorites')
def get_favorites():
    if 'username' not in session:
        return jsonify([])

    user = users_col.find_one({"username": session['username']})
    fav_ids = user.get('favorites', [])

    obj_ids = []
    for f_id in fav_ids:
        try:
            obj_ids.append(ObjectId(f_id))
        except:
            continue

    fav_products = list(products_col.find({"_id": {"$in": obj_ids}}))

    for p in fav_products:
        p['_id'] = str(p['_id'])
        seller = users_col.find_one({"_id": ObjectId(p.get('seller_id'))}) if p.get('seller_id') else None
        p['seller_rating'] = seller.get('avg_rating', 0) if seller else 0
        p['seller_badge'] = seller.get('blue_badge', False) if seller else False

    return jsonify(fav_products)

@app.route('/social-auth/<provider>')
def social_auth(provider):
    return jsonify({
        "status": "pending",
        "message": f"OAuth configuration for {provider} is required.",
        "action": "Please add Client ID and Client Secret from developer console."
    }), 501

@app.route('/github-login')
def github_login():
    github_auth_url = f"https://github.com/login/oauth/authorize?client_id={GITHUB_CLIENT_ID}&scope=user:email"
    return redirect(github_auth_url)


@app.route('/github-callback')
def github_callback():
    code = request.args.get('code')
    if not code:
        return redirect('/login-page')

    token_url = 'https://github.com/login/oauth/access_token'
    payload = {
        'client_id': GITHUB_CLIENT_ID,
        'client_secret': GITHUB_CLIENT_SECRET,
        'code': code
    }
    headers = {'Accept': 'application/json'}

    res = requests.post(token_url, data=payload, headers=headers)
    token_data = res.json()
    access_token = token_data.get('access_token')

    if not access_token:
        return redirect('/login-page')

    user_url = 'https://api.github.com/user'
    user_headers = {'Authorization': f'Bearer {access_token}'}
    user_res = requests.get(user_url, headers=user_headers)
    github_user = user_res.json()

    emails_res = requests.get(f'{user_url}/emails', headers=user_headers)
    emails_data = emails_res.json()
    primary_email = next((e['email'] for e in emails_data if e.get('primary')), '')

    github_id = str(github_user.get('id'))
    name = github_user.get('name') or github_user.get('login')
    avatar = github_user.get('avatar_url', '')

    user = users_col.find_one({"$or": [{"email": primary_email}, {"github_id": github_id}]}) if primary_email else users_col.find_one({"github_id": github_id})

    if not user:
        new_user = {
            "username": name,
            "email": primary_email,
            "password": "",
            "created_at": datetime.now(),
            "is_verified": True,
            "verification_code": "",
            "avatar": avatar,
            "avg_rating": 0,
            "reviews": [],
            "wallet_balance": 100,
            "github_id": github_id
        }
        result = users_col.insert_one(new_user)
        session['username'] = new_user['username']
        session['user_id'] = str(result.inserted_id)
    else:
        if not user.get('github_id'):
            users_col.update_one({"_id": user['_id']}, {"$set": {"github_id": github_id, "avatar": avatar if not user.get('avatar') else user['avatar']}})
        session['username'] = user['username']
        session['user_id'] = str(user['_id'])

    return redirect('/')

@app.route('/discord-login')
def discord_login():
    discord_auth_url = f"https://discord.com/api/oauth2/authorize?client_id={DISCORD_CLIENT_ID}&redirect_uri={DISCORD_REDIRECT_URI}&response_type=code&scope=identify%20email"
    return redirect(discord_auth_url)


@app.route('/discord-callback')
def discord_callback():
    code = request.args.get('code')
    if not code:
        return redirect('/login-page')

    token_url = 'https://discord.com/api/oauth2/token'
    data = {
        'client_id': DISCORD_CLIENT_ID,
        'client_secret': DISCORD_CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': DISCORD_REDIRECT_URI
    }
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}

    res = requests.post(token_url, data=data, headers=headers)
    token_data = res.json()
    access_token = token_data.get('access_token')

    if not access_token:
        return redirect('/login-page')

    user_url = 'https://discord.com/api/users/@me'
    user_headers = {'Authorization': f'Bearer {access_token}'}
    user_res = requests.get(user_url, headers=user_headers)
    discord_user = user_res.json()

    discord_id = str(discord_user.get('id'))
    name = discord_user.get('username')
    email = discord_user.get('email', '')
    avatar_hash = discord_user.get('avatar')

    avatar_url = ''
    if avatar_hash:
        avatar_url = f"https://cdn.discordapp.com/avatars/{discord_id}/{avatar_hash}.png"

    user = users_col.find_one({"$or": [{"email": email}, {"discord_id": discord_id}]}) if email else users_col.find_one({"discord_id": discord_id})

    if not user:
        new_user = {
            "username": name,
            "email": email,
            "password": "",
            "created_at": datetime.now(),
            "is_verified": True,
            "verification_code": "",
            "avatar": avatar_url,
            "avg_rating": 0,
            "reviews": [],
            "wallet_balance": 100,
            "discord_id": discord_id
        }
        result = users_col.insert_one(new_user)
        session['username'] = new_user['username']
        session['user_id'] = str(result.inserted_id)
    else:
        if not user.get('discord_id'):
            users_col.update_one({"_id": user['_id']}, {"$set": {"discord_id": discord_id, "avatar": avatar_url if not user.get('avatar') else user['avatar']}})
        session['username'] = user['username']
        session['user_id'] = str(user['_id'])

    return redirect('/')
@app.route('/checkout', methods=['POST'])
def checkout():
    if 'username' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json
    product_id = data.get('product_id')
    buyer_id = session['user_id']

    product = products_col.find_one({"_id": ObjectId(product_id), "status": "available"})
    if not product:
        return jsonify({"error": "Product is no longer available"}), 400

    if str(product['seller_id']) == buyer_id:
        return jsonify({"error": "You cannot buy your own product"}), 400

    buyer = users_col.find_one({"_id": ObjectId(buyer_id)})
    price = product['price']

    if buyer.get('wallet_balance', 0) < price:
        return jsonify({"error": "Insufficient funds in your wallet"}), 400

    fee = price * FEE_PERCENT
    seller_receives = price - fee

    users_col.update_one(
        {"_id": ObjectId(buyer_id)},
        {"$inc": {"wallet_balance": -price}}
    )

    new_order = {
        "product_id": product_id,
        "product_title": product['title'],
        "buyer_id": buyer_id,
        "seller_id": str(product['seller_id']),
        "price": price,
        "platform_fee": fee,
        "seller_receives": seller_receives,
        "currency": product['currency'],
        "status": "pending_tracking",
        "tracking_number": "",
        "created_at": datetime.now(),
        "tracking_deadline": datetime.now() + timedelta(days=TRACKING_DEADLINE_DAYS)
    }
    orders_col.insert_one(new_order)

    products_col.update_one(
        {"_id": ObjectId(product_id)},
        {"$set": {"status": "escrow"}}
    )

    return jsonify({"message": "Payment secured in Escrow. Waiting for seller to ship!"}), 200


@app.route('/add-tracking', methods=['POST'])
def add_tracking():
    if 'username' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json
    order_id = data.get('order_id')
    tracking_num = data.get('tracking_number')

    order = orders_col.find_one(
        {"_id": ObjectId(order_id), "seller_id": session['user_id'], "status": "pending_tracking"})
    if not order:
        return jsonify({"error": "Order not found or tracking already provided"}), 404

    orders_col.update_one(
        {"_id": ObjectId(order_id)},
        {"$set": {"tracking_number": tracking_num, "status": "shipped"}}
    )
    return jsonify({"message": "Tracking added! Buyer has been notified."}), 200


@app.route('/confirm-delivery', methods=['POST'])
def confirm_delivery():
    if 'username' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json
    order_id = data.get('order_id')

    order = orders_col.find_one({"_id": ObjectId(order_id), "buyer_id": session['user_id'], "status": "shipped"})
    if not order:
        return jsonify({"error": "Order not found or not in shipped status"}), 404

    users_col.update_one(
        {"_id": ObjectId(order['seller_id'])},
        {"$inc": {"wallet_balance": order['seller_receives']}}
    )

    orders_col.update_one(
        {"_id": ObjectId(order_id)},
        {"$set": {"status": "completed", "completed_at": datetime.now()}}
    )

    products_col.update_one(
        {"_id": ObjectId(order['product_id'])},
        {"$set": {"status": "sold", "buyer_id": session['user_id']}}
    )

    return jsonify({"message": "Delivery confirmed. Funds released to seller!"}), 200


@app.route('/check-expired-escrow', methods=['POST'])
def check_expired_escrow():
    expired_orders = orders_col.find({
        "status": "pending_tracking",
        "tracking_deadline": {"$lt": datetime.now()}
    })

    refund_count = 0
    for order in expired_orders:
        users_col.update_one(
            {"_id": ObjectId(order['buyer_id'])},
            {"$inc": {"wallet_balance": order['price']}}
        )

        orders_col.update_one(
            {"_id": order['_id']},
            {"$set": {"status": "refunded", "refunded_at": datetime.now()}}
        )

        products_col.update_one(
            {"_id": ObjectId(order['product_id'])},
            {"$set": {"status": "available"}}
        )
        refund_count += 1

    return jsonify({"message": f"{refund_count} orders auto-refunded to buyers due to shipping timeout."}), 200


@app.route('/orders')
def orders_dashboard():
    if 'username' not in session:
        return redirect('/login-page')

    user_id = session['user_id']

    bought_orders = list(orders_col.find({"buyer_id": user_id}).sort("created_at", -1))
    sold_orders = list(orders_col.find({"seller_id": user_id}).sort("created_at", -1))

    for order in bought_orders + sold_orders:
        order['_id'] = str(order['_id'])
        order['created_at_str'] = order['created_at'].strftime("%Y-%m-%d %H:%M")
        if 'expires_at' in order:
            order['expires_at_iso'] = order['expires_at'].isoformat()
        if 'paid_at' in order:
            order['shipping_deadline_iso'] = (order['paid_at'] + timedelta(days=3)).isoformat()

    return render_template('orders.html', bought=bought_orders, sold=sold_orders, user=session['username'])


@app.route('/api/order-status/<order_id>')
def order_status_api(order_id):
    if 'username' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    order = orders_col.find_one({"_id": ObjectId(order_id)})
    if not order:
        return jsonify({"error": "Not found"}), 404

    return jsonify({"status": order.get('status')})


@app.route('/request-escrow-payment', methods=['POST'])
@app.route('/request-escrow-payment', methods=['POST'])
def request_escrow_payment():
    if 'username' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json
    product_id = data.get('product_id')
    product = products_col.find_one({"_id": ObjectId(product_id)})

    product_currency = product.get('currency', 'BTC')
    platform_wallet_info = PLATFORM_WALLETS.get(product_currency)

    if not platform_wallet_info:
        return jsonify({"error": f"Platform wallet for {product_currency} is not configured."}), 400

    platform_address = platform_wallet_info['address']
    platform_network = platform_wallet_info['network']

    seller = users_col.find_one({"_id": ObjectId(product['seller_id'])})
    seller_wallets = seller.get('payout_wallets', [])

    matching_wallet = next((w for w in seller_wallets if w.get('currency') == product_currency), None)

    if not matching_wallet:
        return jsonify({"error": "Seller no longer has a matching payout wallet for this currency."}), 400

    expires_at = datetime.now() + timedelta(minutes=30)

    new_order = {
        "product_id": product_id,
        "product_title": product['title'],
        "buyer_id": session['user_id'],
        "seller_id": str(product['seller_id']),
        "seller_wallet": matching_wallet['address'],
        "seller_network": matching_wallet['network'],
        "price": product['price'],
        "currency": product_currency,
        "status": "awaiting_payment",
        "payment_address": platform_address,
        "payment_network": platform_network,
        "expires_at": expires_at,
        "created_at": datetime.now()
    }

    order_id = orders_col.insert_one(new_order).inserted_id

    products_col.update_one(
        {"_id": ObjectId(product_id)},
        {"$set": {"status": "hold"}}
    )

    return jsonify({
        "order_id": str(order_id),
        "payment_address": platform_address,
        "payment_network": platform_network,
        "currency": product_currency,
        "expires_in_minutes": 30
    }), 200


# Automated Background Task (Runs every 1 minute)
@scheduler.task('interval', id='monitor_orders', minutes=1)
def monitor_orders():
    with app.app_context():
        pending_payments = orders_col.find({"status": "awaiting_payment"})
        for order in pending_payments:
            if datetime.now() > order['expires_at']:
                orders_col.update_one({"_id": order['_id']}, {"$set": {"status": "expired"}})

                products_col.update_one(
                    {"_id": ObjectId(order['product_id'])},
                    {"$set": {"status": "available"}}
                )
                continue

            if check_blockchain_for_payment(order['payment_address'], order['price']):
                orders_col.update_one({"_id": order['_id']},
                                      {"$set": {"status": "pending_tracking", "paid_at": datetime.now()}})

                products_col.update_one(
                    {"_id": ObjectId(order['product_id'])},
                    {"$set": {"status": "sold", "buyer_id": order['buyer_id']}}
                )

        unshipped_orders = orders_col.find({
            "status": "pending_tracking",
            "paid_at": {"$lt": datetime.now() - timedelta(days=3)}
        })

        for order in unshipped_orders:
            refund_amount = order['price'] * (1 - FEE_PERCENT)
            orders_col.update_one({"_id": order['_id']},
                                  {"$set": {"status": "refunded", "refund_amount": refund_amount}})

            products_col.update_one(
                {"_id": ObjectId(order['product_id'])},
                {"$set": {"status": "available", "buyer_id": ""}}
            )


import uuid


@app.route('/add-payout-wallet', methods=['POST'])
def add_payout_wallet():
    if 'username' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json
    currency = data.get('currency')
    network = data.get('network')
    address = data.get('address')

    if not currency or not network or not address:
        return jsonify({"error": "Missing wallet details"}), 400

    new_wallet = {
        "id": str(uuid.uuid4()),
        "currency": currency,
        "network": network,
        "address": address,
        "added_at": datetime.now()
    }

    users_col.update_one(
        {"_id": ObjectId(session['user_id'])},
        {"$push": {"payout_wallets": new_wallet}}
    )

    return jsonify({"message": "Wallet saved successfully!"}), 200


@app.route('/delete-payout-wallet/<wallet_id>', methods=['POST'])
def delete_payout_wallet(wallet_id):
    if 'username' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    users_col.update_one(
        {"_id": ObjectId(session['user_id'])},
        {"$pull": {"payout_wallets": {"id": wallet_id}}}
    )
    return jsonify({"message": "Wallet removed"}), 200

def check_blockchain_for_payment(address, expected_amount):
    # This is a placeholder for real blockchain integration
    return False


scheduler.init_app(app)
scheduler.start()

if __name__ == '__main__':
    app.run(debug=True, port=5000)