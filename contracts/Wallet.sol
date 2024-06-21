// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract Wallet {
    struct User {
        string username;
        string password;
    }

    mapping(string => bool) private users;

    event UserRegistered(string username);
    event FundsDeposited(address indexed from, uint256 value);
    event FundsTransferred(address indexed from, address indexed to, uint256 value);

    function register(string memory _username, string memory _password) public {
        require(!users[_username], "User already exists");
        users[_username] = true;
        // Additional logic to store the password (hashed or otherwise)
        emit UserRegistered(_username);
    }

    function userExists(string memory _username) public view returns (bool) {
        return users[_username];
    }

    function depositFunds() public payable {
        emit FundsDeposited(msg.sender, msg.value);
    }

    function transferFunds(address payable _to, uint256 _amount, string memory _password) public {
        // Add logic to verify the password and transfer funds
        require(_to != address(0), "Invalid address");
        require(address(this).balance >= _amount, "Insufficient balance");
        
        _to.transfer(_amount);
        emit FundsTransferred(msg.sender, _to, _amount);
    }
}
