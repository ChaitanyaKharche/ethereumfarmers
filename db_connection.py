import mysql.connector
import os

def connect():
    return mysql.connector.connect(
        host="localhost",
        user="root",           # use the root username
        password="123456",     # use the password for the root user
        database="farmeasy"    # the database you created
    )


def get_db_connection():
    return connect()
