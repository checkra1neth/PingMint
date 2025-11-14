#!/usr/bin/env python3
"""
Batch NFT Transfer Script
Sends multiple NFTs to one address in a single transaction or quickly in sequence
"""

import os
import sys
import time
from dotenv import load_dotenv
from web3 import Web3

load_dotenv()

# Contract addresses on Base
NETPACKETS_CONTRACT = "0x4daBb4f0BCEc4Ece9fE4a8F5d709DA9CDc78bAE1"

# Minimal ABI for transfers
NETPACKETS_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "from", "type": "address"},
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "tokenId", "type": "uint256"}
        ],
        "name": "transferFrom",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "address", "name": "from", "type": "address"},
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256[]", "name": "tokenIds", "type": "uint256[]"}
        ],
        "name": "batchTransferFrom",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]


class BatchTransfer:
    def __init__(self):
        self.rpc_url = os.getenv("BASE_RPC_URL", "https://mainnet.base.org")
        private_key = os.getenv("PRIVATE_KEY")
        
        if not private_key:
            raise ValueError("PRIVATE_KEY not found in .env file")
        
        if not private_key.startswith("0x"):
            private_key = "0x" + private_key
            
        self.private_key = private_key
        
        # Initialize Web3
        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))
        
        if not self.w3.is_connected():
            raise ConnectionError("Failed to connect to Base network")
        
        # Setup account
        self.account = self.w3.eth.account.from_key(self.private_key)
        self.address = self.account.address
        
        # Initialize contract
        self.netpackets = self.w3.eth.contract(
            address=Web3.to_checksum_address(NETPACKETS_CONTRACT),
            abi=NETPACKETS_ABI
        )
        
        print(f"✅ Connected to Base network")
        print(f"📍 Wallet address: {self.address}")
        print(f"💰 ETH Balance: {self.w3.from_wei(self.w3.eth.get_balance(self.address), 'ether')} ETH\n")
    
    def get_my_nfts(self, method="events", blocks_back=50000):
        """Get list of NFT token IDs owned by this wallet
        
        Args:
            method: "events" (fast, recommended) or "scan" (slow, checks all IDs)
            blocks_back: How many blocks back to check for Transfer events
        """
        if method == "events":
            return self._get_nfts_from_events(blocks_back)
        else:
            return self._get_nfts_by_scanning()
    
    def _get_nfts_from_events(self, blocks_back=50000):
        """Fast method: Get NFTs by scanning Transfer events"""
        print(f"🔍 Scanning Transfer events (last {blocks_back:,} blocks)...")
        
        current_block = self.w3.eth.block_number
        from_block = max(0, current_block - blocks_back)
        
        # Transfer event signature: Transfer(address indexed from, address indexed to, uint256 indexed tokenId)
        transfer_topic = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
        
        # Get all transfers TO this address
        print(f"  📥 Checking transfers TO your wallet...")
        my_address_padded = "0x" + self.address[2:].lower().zfill(64)
        
        potential_nfts = set()
        
        try:
            # Get logs in chunks to avoid RPC limits
            chunk_size = 10000
            for chunk_start in range(from_block, current_block + 1, chunk_size):
                chunk_end = min(chunk_start + chunk_size - 1, current_block)
                
                logs = self.w3.eth.get_logs({
                    'fromBlock': chunk_start,
                    'toBlock': chunk_end,
                    'address': NETPACKETS_CONTRACT,
                    'topics': [transfer_topic, None, my_address_padded]
                })
                
                for log in logs:
                    if len(log['topics']) >= 4:
                        token_id = int(log['topics'][3].hex(), 16)
                        potential_nfts.add(token_id)
                
                if chunk_end >= current_block:
                    break
                    
                print(f"  ⏳ Processed blocks {chunk_start:,} - {chunk_end:,}, found {len(potential_nfts)} potential NFTs...")
        
        except Exception as e:
            print(f"  ⚠️  Error getting events: {e}")
            print(f"  💡 Falling back to direct balance check...")
            return self._get_nfts_by_balance()
        
        print(f"  ✅ Found {len(potential_nfts)} NFTs received")
        
        # Now verify which ones we still own
        if not potential_nfts:
            return []
        
        print(f"  🔍 Verifying current ownership...")
        my_nfts = []
        
        for token_id in sorted(potential_nfts):
            try:
                owner = self.netpackets.functions.ownerOf(token_id).call()
                if owner.lower() == self.address.lower():
                    my_nfts.append(token_id)
            except Exception:
                # Token might have been burned
                pass
        
        print(f"✅ You currently own {len(my_nfts)} NFTs")
        if my_nfts:
            preview = my_nfts[:10]
            preview_str = ", ".join(map(str, preview))
            if len(my_nfts) > 10:
                preview_str += f", ... (+{len(my_nfts) - 10} more)"
            print(f"📦 Your NFTs: {preview_str}\n")
        
        return my_nfts
    
    def _get_nfts_by_balance(self):
        """Try to get NFTs using balanceOf and tokenOfOwnerByIndex if available"""
        try:
            balance = self.netpackets.functions.balanceOf(self.address).call()
            print(f"  📊 Balance shows: {balance} NFTs")
            
            if balance == 0:
                return []
            
            # Contract might not have tokenOfOwnerByIndex, so we'll need manual scan
            print(f"  ⚠️  Cannot get specific token IDs automatically")
            print(f"  💡 Please use manual mode or increase scan range\n")
            return []
            
        except Exception as e:
            print(f"  ⚠️  Could not check balance: {e}")
            return []
    
    def _get_nfts_by_scanning(self, max_check=5000):
        """Slow method: Check each token ID individually"""
        print(f"🔍 Scanning token IDs (checking up to #{max_check})...")
        
        my_nfts = []
        checked = 0
        
        for token_id in range(1, max_check + 1):
            try:
                owner = self.netpackets.functions.ownerOf(token_id).call()
                if owner.lower() == self.address.lower():
                    my_nfts.append(token_id)
                checked += 1
                
                if checked % 100 == 0:
                    print(f"  ⏳ Checked {checked} tokens, found {len(my_nfts)} yours...")
                    
            except Exception:
                pass
        
        print(f"✅ Found {len(my_nfts)} NFTs in your wallet")
        if my_nfts:
            preview = my_nfts[:10]
            preview_str = ", ".join(map(str, preview))
            if len(my_nfts) > 10:
                preview_str += f", ... (+{len(my_nfts) - 10} more)"
            print(f"📦 Your NFTs: {preview_str}\n")
        
        return my_nfts
    
    def batch_transfer_single_tx(self, token_ids, to_address):
        """Transfer multiple NFTs in a single transaction using batchTransferFrom"""
        print(f"\n{'='*60}")
        print(f"🎁 BATCH TRANSFER (Single Transaction)")
        print(f"{'='*60}")
        print(f"📦 Token IDs: {', '.join(map(str, token_ids))}")
        print(f"📬 To: {to_address}")
        print(f"{'='*60}\n")
        
        try:
            # Build batch transfer transaction
            tx = self.netpackets.functions.batchTransferFrom(
                self.address,
                Web3.to_checksum_address(to_address),
                token_ids
            ).build_transaction({
                'from': self.address,
                'nonce': self.w3.eth.get_transaction_count(self.address),
            })
            
            # Display gas info
            base_fee = self.w3.eth.get_block('latest')['baseFeePerGas']
            print(f"⛽ Network base fee: {self.w3.from_wei(base_fee, 'gwei'):.2f} Gwei")
            print(f"⛽ Estimated gas: {tx.get('gas', 'auto')}")
            
            # Sign and send
            signed_tx = self.w3.eth.account.sign_transaction(tx, self.private_key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            
            print(f"\n📤 Batch Transfer TX: {tx_hash.hex()}")
            print(f"🔗 https://basescan.org/tx/{tx_hash.hex()}")
            
            # Wait for confirmation
            print(f"\n⏳ Waiting for confirmation...")
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
            
            if receipt['status'] == 1:
                gas_used = receipt['gasUsed']
                effective_gas_price = receipt['effectiveGasPrice']
                gas_price_gwei = self.w3.from_wei(effective_gas_price, 'gwei')
                gas_cost_eth = self.w3.from_wei(gas_used * effective_gas_price, 'ether')
                
                print(f"\n✅ Batch transfer successful!")
                print(f"📦 Transferred {len(token_ids)} NFTs in one transaction")
                print(f"⛽ Gas used: {gas_used} ({gas_price_gwei:.2f} Gwei)")
                print(f"💸 Total cost: {gas_cost_eth:.6f} ETH")
                print(f"💡 Cost per NFT: {gas_cost_eth/len(token_ids):.8f} ETH")
                return True
            else:
                print(f"\n❌ Batch transfer failed!")
                return False
                
        except Exception as e:
            error_msg = str(e)
            if "batchTransferFrom" in error_msg or "not found" in error_msg.lower():
                print(f"\n⚠️  Contract doesn't support batchTransferFrom")
                print(f"💡 Falling back to rapid sequential transfers...\n")
                return self.rapid_sequential_transfer(token_ids, to_address)
            else:
                print(f"\n❌ Error in batch transfer: {e}")
                return False
    
    def rapid_sequential_transfer(self, token_ids, to_address):
        """Transfer multiple NFTs rapidly in sequence (pre-build all transactions)"""
        print(f"\n{'='*60}")
        print(f"⚡ RAPID SEQUENTIAL TRANSFER")
        print(f"{'='*60}")
        print(f"📦 Token IDs: {', '.join(map(str, token_ids))}")
        print(f"📬 To: {to_address}")
        print(f"{'='*60}\n")
        
        base_nonce = self.w3.eth.get_transaction_count(self.address)
        transactions = []
        
        print(f"🔨 Building {len(token_ids)} transactions...")
        
        # Pre-build all transactions with sequential nonces
        for idx, token_id in enumerate(token_ids):
            try:
                tx = self.netpackets.functions.transferFrom(
                    self.address,
                    Web3.to_checksum_address(to_address),
                    token_id
                ).build_transaction({
                    'from': self.address,
                    'nonce': base_nonce + idx,
                })
                transactions.append((token_id, tx))
                print(f"  ✓ TX {idx+1}/{len(token_ids)} built (Token #{token_id}, nonce: {base_nonce + idx})")
            except Exception as e:
                print(f"  ✗ Failed to build TX for token #{token_id}: {e}")
                return False
        
        print(f"\n📤 Sending {len(transactions)} transactions rapidly...")
        
        sent_hashes = []
        total_gas_used = 0
        total_cost = 0
        
        # Send all transactions as fast as possible
        for idx, (token_id, tx) in enumerate(transactions):
            try:
                signed_tx = self.w3.eth.account.sign_transaction(tx, self.private_key)
                tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
                sent_hashes.append((token_id, tx_hash))
                print(f"  ✓ Sent {idx+1}/{len(transactions)}: Token #{token_id} | {tx_hash.hex()[:16]}...")
            except Exception as e:
                print(f"  ✗ Failed to send token #{token_id}: {e}")
        
        print(f"\n⏳ Waiting for all {len(sent_hashes)} transactions to confirm...")
        
        successful = 0
        failed = 0
        
        # Wait for all confirmations
        for idx, (token_id, tx_hash) in enumerate(sent_hashes):
            try:
                print(f"  ⏳ Waiting for TX {idx+1}/{len(sent_hashes)}...", end=" ")
                receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
                
                if receipt['status'] == 1:
                    gas_used = receipt['gasUsed']
                    effective_gas_price = receipt['effectiveGasPrice']
                    cost = gas_used * effective_gas_price
                    total_gas_used += gas_used
                    total_cost += cost
                    successful += 1
                    print(f"✅")
                else:
                    failed += 1
                    print(f"❌")
            except Exception as e:
                failed += 1
                print(f"❌ Timeout or error")
        
        # Summary
        print(f"\n{'='*60}")
        print(f"📊 RAPID TRANSFER SUMMARY")
        print(f"{'='*60}")
        print(f"✅ Successful: {successful}/{len(token_ids)}")
        print(f"❌ Failed: {failed}/{len(token_ids)}")
        print(f"⛽ Total gas used: {total_gas_used:,}")
        print(f"💸 Total cost: {self.w3.from_wei(total_cost, 'ether'):.6f} ETH")
        if successful > 0:
            print(f"💡 Average cost per NFT: {self.w3.from_wei(total_cost/successful, 'ether'):.8f} ETH")
        print(f"{'='*60}\n")
        
        return successful == len(token_ids)
    
    def transfer_to_multiple(self, token_ids, addresses):
        """Transfer NFTs to multiple addresses (one NFT per address)"""
        if len(token_ids) != len(addresses):
            print(f"⚠️  Warning: {len(token_ids)} tokens but {len(addresses)} addresses")
            min_count = min(len(token_ids), len(addresses))
            token_ids = token_ids[:min_count]
            addresses = addresses[:min_count]
        
        print(f"\n{'='*60}")
        print(f"🎁 MULTI-RECIPIENT TRANSFER")
        print(f"{'='*60}")
        print(f"📦 Transferring {len(token_ids)} NFTs to {len(addresses)} addresses")
        print(f"{'='*60}\n")
        
        base_nonce = self.w3.eth.get_transaction_count(self.address)
        sent_hashes = []
        
        print(f"📤 Sending transactions...")
        
        for idx, (token_id, to_address) in enumerate(zip(token_ids, addresses)):
            try:
                tx = self.netpackets.functions.transferFrom(
                    self.address,
                    Web3.to_checksum_address(to_address),
                    token_id
                ).build_transaction({
                    'from': self.address,
                    'nonce': base_nonce + idx,
                })
                
                signed_tx = self.w3.eth.account.sign_transaction(tx, self.private_key)
                tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
                sent_hashes.append((token_id, to_address, tx_hash))
                print(f"  ✓ {idx+1}/{len(token_ids)}: Token #{token_id} → {to_address[:10]}...{to_address[-8:]}")
            except Exception as e:
                print(f"  ✗ Failed token #{token_id}: {e}")
        
        print(f"\n⏳ Waiting for confirmations...")
        
        successful = 0
        for idx, (token_id, to_address, tx_hash) in enumerate(sent_hashes):
            try:
                receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
                if receipt['status'] == 1:
                    successful += 1
                    print(f"  ✅ {idx+1}/{len(sent_hashes)}: Token #{token_id} transferred")
            except:
                print(f"  ❌ {idx+1}/{len(sent_hashes)}: Token #{token_id} failed")
        
        print(f"\n✅ Successfully transferred {successful}/{len(token_ids)} NFTs\n")
        return successful == len(token_ids)


def main():
    print("🎁 Batch NFT Transfer Tool\n")
    
    try:
        batch = BatchTransfer()
        
        print("Choose input mode:")
        print("1. Auto-detect my NFTs (just enter count + address)")
        print("2. Manual token IDs (enter specific IDs)")
        
        input_mode = input("\nEnter mode (1 or 2): ").strip()
        
        if input_mode == "1":
            # Auto-detect NFTs
            my_nfts = batch.get_my_nfts()
            
            if not my_nfts:
                print("❌ No NFTs found in your wallet!")
                return
            
            print("Choose transfer mode:")
            print("1. Transfer to ONE address")
            print("2. Transfer to MULTIPLE addresses")
            
            mode = input("\nEnter mode (1 or 2): ").strip()
            
            if mode == "1":
                # Transfer to one address
                count = input(f"\nHow many NFTs to transfer? (max {len(my_nfts)}): ").strip()
                count = int(count)
                
                if count > len(my_nfts):
                    print(f"⚠️  You only have {len(my_nfts)} NFTs. Transferring all.")
                    count = len(my_nfts)
                
                token_ids = my_nfts[:count]
                to_address = input("Enter recipient address: ").strip()
                
                print(f"\n📦 Will transfer {len(token_ids)} NFTs to {to_address}")
                print(f"🎫 Token IDs: {', '.join(map(str, token_ids))}")
                confirm = input("\nProceed? (y/n): ").strip().lower()
                
                if confirm == 'y':
                    batch.batch_transfer_single_tx(token_ids, to_address)
            
            elif mode == "2":
                # Transfer to multiple addresses
                addresses_input = input("\nEnter addresses (comma-separated): ").strip()
                addresses = [x.strip() for x in addresses_input.split(",") if x.strip()]
                
                count = min(len(my_nfts), len(addresses))
                token_ids = my_nfts[:count]
                
                print(f"\n📦 Will transfer {count} NFTs to {len(addresses)} addresses")
                confirm = input("Proceed? (y/n): ").strip().lower()
                
                if confirm == 'y':
                    batch.transfer_to_multiple(token_ids, addresses)
        
        elif input_mode == "2":
            # Manual mode
            print("\nChoose transfer mode:")
            print("1. Batch transfer to ONE address")
            print("2. Transfer to MULTIPLE addresses")
            
            mode = input("\nEnter mode (1 or 2): ").strip()
            
            if mode == "1":
                # Batch to one address
                token_ids_input = input("\nEnter token IDs (comma-separated): ").strip()
                token_ids = [int(x.strip()) for x in token_ids_input.split(",") if x.strip()]
                
                to_address = input("Enter recipient address: ").strip()
                
                print(f"\n📦 Will transfer {len(token_ids)} NFTs to {to_address}")
                confirm = input("Proceed? (y/n): ").strip().lower()
                
                if confirm == 'y':
                    batch.batch_transfer_single_tx(token_ids, to_address)
        
            elif mode == "2":
                # Multiple addresses
                token_ids_input = input("\nEnter token IDs (comma-separated): ").strip()
                token_ids = [int(x.strip()) for x in token_ids_input.split(",") if x.strip()]
                
                addresses_input = input("Enter addresses (comma-separated): ").strip()
                addresses = [x.strip() for x in addresses_input.split(",") if x.strip()]
                
                print(f"\n📦 Will transfer {len(token_ids)} NFTs to {len(addresses)} addresses")
                confirm = input("Proceed? (y/n): ").strip().lower()
                
                if confirm == 'y':
                    batch.transfer_to_multiple(token_ids, addresses)
        
        else:
            print("Invalid input mode selected")
            
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
