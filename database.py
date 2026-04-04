import pymongo
from datetime import datetime


client = pymongo.MongoClient("mongodb://localhost:27017/")

# 2. בחירת מסד הנתונים שיצרנו
db = client["CryptoMarketplace"]

# 3. הגדרת האוספים (Collections) כדי שיהיה נוח לעבוד איתם
users_col = db["users"]
products_col = db["products"]
chats_col = db["chats"]


# --- פונקציות לעבודה עם הנתונים ---

def create_user(username, email, password):
    """
    פונקציה שמקבלת פרטים ויוצרת משתמש חדש
    """
    # הכנת המידע בפורמט של מילון (כמו JSON)
    new_user = {
        "username": username,
        "email": email,
        "password": password,  # הערה: בפרויקט אמיתי מצפינים את הסיסמה!
        "wallet_address": "",  # כרגע ריק, המשתמש יוסיף אחר כך
        "created_at": datetime.now()  # תאריך ושעה עכשווים
    }

    # הכנסת הנתונים לדאטה-בייס
    result = users_col.insert_one(new_user)

    # הדפסה למסך כדי שנדע שזה הצליח
    print(f"User created successfully! ID: {result.inserted_id}")




def create_product(seller_username, title, description, price, currency="BTC"):
    """
    פונקציה שמוסיפה מוצר חדש למערכת
    """
    # קודם כל, נבדוק אם המוכר קיים בכלל במערכת
    # אנחנו מחפשים משתמש לפי השם שלו
    seller = users_col.find_one({"username": seller_username})

    if not seller:
        print(f"Error: Seller '{seller_username}' not found!")
        return

    # יצירת מילון עם פרטי המוצר
    new_product = {
        "seller_id": seller["_id"],  # אנחנו מקשרים את המוצר ל-ID האמיתי של המשתמש במסד הנתונים
        "seller_name": seller_username,  # שומרים גם את השם שיהיה קל להציג
        "title": title,
        "description": description,
        "price": price,
        "currency": currency,
        "is_promoted": False,  # ברירת מחדל - לא מקודם
        "created_at": datetime.now()
    }

    # הכנסה למסד הנתונים
    result = products_col.insert_one(new_product)
    print(f"Product '{title}' added successfully! ID: {result.inserted_id}")


# --- הרצת בדיקה ---
# זה ירוץ רק כשנפעיל את הקובץ ישירות
if __name__ == "__main__":
    print("Connecting to DB...")
    # ננסה ליצור משתמש חדש דרך הקוד
    #create_user("PythonUser", "code@test.com", "secret123")
    create_product(seller_username="PythonUser",title="Gaming Laptop Lenovo",description="מחשב גיימינג חזק, כרטיס מסך 4060",price=0.025)