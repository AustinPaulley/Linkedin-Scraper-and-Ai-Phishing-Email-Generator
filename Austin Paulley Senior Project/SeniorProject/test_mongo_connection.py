from pymongo import MongoClient

print("Starting connection test...")

try:
    client = MongoClient("mongodb+srv://austin:TSMBoy2002%21@cluster0.1rnkv.mongodb.net/test")
    print("Connected to MongoDB!")
except Exception as e:
    print(f"Error: {e}")

print("Test complete.")
