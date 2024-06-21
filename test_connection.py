import mysql.connector

def connect():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="123456",
        database="farmeasy"
    )

try:
    connection = connect()
    print("Connection successful")
    connection.close()
except mysql.connector.Error as err:
    print(f"Error: {err}")
