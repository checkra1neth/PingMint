#!/usr/bin/env python3
"""
NetPackets NFT Minter
Automatically mints NetPackets NFTs on Base network
"""

import os
import sys
import time
from decimal import Decimal
from dotenv import load_dotenv
from web3 import Web3

load_dotenv()

# Contract addresses on Base
NETPACKETS_CONTRACT = "0x4daBb4f0BCEc4Ece9fE4a8F5d709DA9CDc78bAE1"
USDC_CONTRACT = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"

# ABIs
ERC20_ABI = [
    {
        "constant": False,
        "inputs": [
            {"name": "_spender", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [
            {"name": "_owner", "type": "address"},
            {"name": "_spender", "type": "address"}
        ],
        "name": "allowance",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    }
]

NETPACKETS_ABI = [
    {
        "inputs": [],
        "name": "mint",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]


class NetPacketsMinter:
    def __init__(self):
        self.rpc_url = os.getenv("BASE_RPC_URL", "https://mainnet.base.org")
        private_key = os.getenv("PRIVATE_KEY")
        
        if not private_key:
            raise ValueError("PRIVATE_KEY not found in .env file")
        
        if not private_key.startswith("0x"):
            private_key = "0x" + private_key
            
        self.private_key = private_key
        self.mint_count = int(os.getenv("MINT_COUNT", "5"))
        
        # Initialize Web3
        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))
        
        if not self.w3.is_connected():
            raise ConnectionError("Failed to connect to Base network")
        
        # Setup account
        self.account = self.w3.eth.account.from_key(self.private_key)
        self.address = self.account.address
        
        # Initialize contracts
        self.usdc = self.w3.eth.contract(
            address=Web3.to_checksum_address(USDC_CONTRACT),
            abi=ERC20_ABI
        )
        self.netpackets = self.w3.eth.contract(
            address=Web3.to_checksum_address(NETPACKETS_CONTRACT),
            abi=NETPACKETS_ABI
        )
        
        print(f"✅ Connected to Base network")
        print(f"📍 Wallet address: {self.address}")
        print(f"💰 ETH Balance: {self.w3.from_wei(self.w3.eth.get_balance(self.address), 'ether')} ETH")
        
    def check_usdc_balance(self):
        """Check USDC balance"""
        balance = self.usdc.functions.balanceOf(self.address).call()
        balance_usdc = balance / 10**6  # USDC has 6 decimals
        print(f"💵 USDC Balance: {balance_usdc} USDC")
        
        required = self.mint_count * 1  # 1 USDC per mint
        if balance_usdc < required:
            print(f"⚠️  Warning: You need at least {required} USDC for {self.mint_count} mints")
            return False
        return True
    
    def approve_usdc(self, amount_usdc):
        """Approve USDC spending"""
        amount_wei = int(amount_usdc * 10**6)  # USDC has 6 decimals
        
        # Check current allowance
        current_allowance = self.usdc.functions.allowance(
            self.address,
            NETPACKETS_CONTRACT
        ).call()
        
        if current_allowance >= amount_wei:
            print(f"✅ USDC already approved (allowance: {current_allowance / 10**6} USDC)")
            return True
        
        print(f"🔄 Approving {amount_usdc} USDC...")
        
        try:
            # Build transaction (gas parameters will be auto-determined)
            tx = self.usdc.functions.approve(
                NETPACKETS_CONTRACT,
                amount_wei
            ).build_transaction({
                'from': self.address,
                'nonce': self.w3.eth.get_transaction_count(self.address),
            })
            
            # Display gas info from network
            base_fee = self.w3.eth.get_block('latest')['baseFeePerGas']
            print(f"⛽ Network base fee: {self.w3.from_wei(base_fee, 'gwei'):.2f} Gwei")
            
            # Sign and send
            signed_tx = self.w3.eth.account.sign_transaction(tx, self.private_key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            
            print(f"📤 Approval TX: {tx_hash.hex()}")
            print(f"🔗 https://basescan.org/tx/{tx_hash.hex()}")
            
            # Wait for confirmation
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            
            if receipt['status'] == 1:
                print(f"✅ Approval successful!")
                return True
            else:
                print(f"❌ Approval failed!")
                return False
                
        except Exception as e:
            print(f"❌ Error approving USDC: {e}")
            return False
    
    def mint_nft(self, mint_number):
        """Mint a single NFT"""
        print(f"\n{'='*50}")
        print(f"🎨 Minting NFT #{mint_number}/{self.mint_count}")
        print(f"{'='*50}")
        
        try:
            # Build transaction (all gas parameters auto-determined by network)
            tx = self.netpackets.functions.mint().build_transaction({
                'from': self.address,
                'nonce': self.w3.eth.get_transaction_count(self.address),
            })
            
            # Display gas info from network
            base_fee = self.w3.eth.get_block('latest')['baseFeePerGas']
            print(f"⛽ Network base fee: {self.w3.from_wei(base_fee, 'gwei'):.2f} Gwei")
            print(f"⛽ Estimated gas: {tx.get('gas', 'auto')}")
            
            # Sign and send
            signed_tx = self.w3.eth.account.sign_transaction(tx, self.private_key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            
            print(f"📤 Mint TX: {tx_hash.hex()}")
            print(f"🔗 https://basescan.org/tx/{tx_hash.hex()}")
            
            # Wait for confirmation
            print(f"⏳ Waiting for confirmation...")
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            
            if receipt['status'] == 1:
                gas_used = receipt['gasUsed']
                effective_gas_price = receipt['effectiveGasPrice']
                gas_price_gwei = self.w3.from_wei(effective_gas_price, 'gwei')
                gas_cost_eth = self.w3.from_wei(gas_used * effective_gas_price, 'ether')
                
                print(f"✅ Mint #{mint_number} successful!")
                print(f"⛽ Gas used: {gas_used} ({gas_price_gwei:.2f} Gwei)")
                print(f"💸 Transaction cost: {gas_cost_eth:.6f} ETH")
                return True
            else:
                print(f"❌ Mint #{mint_number} failed!")
                return False
                
        except Exception as e:
            print(f"❌ Error minting NFT #{mint_number}: {e}")
            return False
    
    def run(self):
        """Main execution flow"""
        print("\n🚀 Starting NetPackets Minter")
        print(f"🎯 Target: {self.mint_count} mints\n")
        
        # Check USDC balance
        if not self.check_usdc_balance():
            response = input("\n❓ Continue anyway? (y/n): ")
            if response.lower() != 'y':
                print("❌ Aborted by user")
                return
        
        # Approve USDC
        total_usdc_needed = self.mint_count * 1
        if not self.approve_usdc(total_usdc_needed):
            print("❌ Failed to approve USDC. Aborting.")
            return
        
        # Wait a bit after approval
        time.sleep(3)
        
        # Mint NFTs
        successful_mints = 0
        failed_mints = 0
        
        for i in range(1, self.mint_count + 1):
            success = self.mint_nft(i)
            
            if success:
                successful_mints += 1
            else:
                failed_mints += 1
                response = input("\n❓ Continue to next mint? (y/n): ")
                if response.lower() != 'y':
                    print("❌ Aborted by user")
                    break
            
            # Wait between mints (except for the last one)
            if i < self.mint_count:
                wait_time = 2
                print(f"\n⏳ Waiting {wait_time} seconds before next mint...")
                time.sleep(wait_time)
        
        # Summary
        print(f"\n{'='*50}")
        print(f"📊 MINTING SUMMARY")
        print(f"{'='*50}")
        print(f"✅ Successful: {successful_mints}")
        print(f"❌ Failed: {failed_mints}")
        print(f"📦 Total: {successful_mints + failed_mints}/{self.mint_count}")
        print(f"{'='*50}\n")


def main():
    try:
        minter = NetPacketsMinter()
        minter.run()
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
