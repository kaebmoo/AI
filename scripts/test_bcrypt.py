import bcrypt

try:
    print(f"Bcrypt version: {bcrypt.__version__}")
except:
    print("Bcrypt version not found")

password = "admin"
try:
    print("Trying bytes...")
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    print("Bytes worked!")
except TypeError as e:
    print(f"Bytes failed: {e}")
    try:
        print("Trying strings...")
        hashed = bcrypt.hashpw(password, bcrypt.gensalt())
        print("Strings worked!")
    except Exception as e2:
        print(f"Strings failed: {e2}")
