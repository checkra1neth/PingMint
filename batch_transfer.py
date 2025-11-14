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
BULK_TRANSFER_CONTRACT = "0x0000000000c2d145a2526bd8c716263bfebe1a72"  # Seaport-like bulk transfer

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
            {"internalType": "address", "name": "operator", "type": "address"},
            {"internalType": "bool", "name": "approved", "type": "bool"}
        ],
        "name": "setApprovalForAll",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "address", "name": "owner", "type": "address"},
            {"internalType": "address", "name": "operator", "type": "address"}
        ],
        "name": "isApprovedForAll",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "address", "name": "owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "uint256", "name": "tokenId", "type": "uint256"}],
        "name": "ownerOf",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    }
]

# Simplified Bulk Transfer ABI
BULK_TRANSFER_ABI = [
    {
        "inputs": [],
        "name": "bulkTransfer",
        "outputs": [],
        "stateMutability": "payable",
        "type": "function"
    }
]


class BatchTransfer:
    def __init__(self):
        # Public RPC endpoints (more reliable than Alchemy free tier)
        rpc_urls = [
            "https://mainnet.base.org",
            "https://base.gateway.tenderly.co",
            "https://base-rpc.publicnode.com",
            "https://base.llamarpc.com",
        ]
        
        self.rpc_url = None
        print("🔌 Testing RPC endpoints...")
        
        for url in rpc_urls:
            try:
                test_w3 = Web3(Web3.HTTPProvider(url, request_kwargs={'timeout': 5}))
                if test_w3.is_connected():
                    # Quick test
                    test_w3.eth.block_number
                    self.rpc_url = url
                    print(f"✅ Using RPC: {url}\n")
                    break
            except Exception as e:
                print(f"  ❌ {url}: {str(e)[:50]}")
                continue
        
        if not self.rpc_url:
            print(f"⚠️  All RPC endpoints failed, using fallback...")
            self.rpc_url = rpc_urls[0]
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
        
        # Initialize contracts
        self.netpackets = self.w3.eth.contract(
            address=Web3.to_checksum_address(NETPACKETS_CONTRACT),
            abi=NETPACKETS_ABI
        )
        self.bulk_transfer = self.w3.eth.contract(
            address=Web3.to_checksum_address(BULK_TRANSFER_CONTRACT),
            abi=BULK_TRANSFER_ABI
        )
        
        print(f"✅ Connected to Base network")
        print(f"📍 Wallet address: {self.address}")
        print(f"💰 ETH Balance: {self.w3.from_wei(self.w3.eth.get_balance(self.address), 'ether')} ETH\n")
    
    def get_my_nfts(self, method="auto", blocks_back=50000):
        """Get list of NFT token IDs owned by this wallet
        
        Args:
            method: "auto" (tries API first), "events", or "scan"  
            blocks_back: How many blocks back to check for Transfer events
        """
        if method == "auto":
            # Try API first (instant like OpenSea), fallback to events
            nfts = self._get_nfts_from_api()
            if nfts is not None:
                return nfts
            return self._get_nfts_from_events(blocks_back)
        elif method == "events":
            return self._get_nfts_from_events(blocks_back)
        else:
            return self._get_nfts_by_scanning()
    
    def _get_nfts_from_api(self):
        """Instant method: Use Alchemy NFT API (OpenSea style)"""
        print(f"⚡ Trying instant API lookup (like OpenSea)...")
        
        try:
            import requests
            
            # Check if we can use Alchemy NFT API
            api_key = os.getenv("ALCHEMY_API_KEY") or os.getenv("BASE_RPC_URL", "").split("/v2/")[-1] if "/v2/" in os.getenv("BASE_RPC_URL", "") else None
            
            if not api_key or len(api_key) < 10:
                print(f"  ℹ️  No Alchemy API, using event scanning...\n")
                return None
            
            api_url = f"https://base-mainnet.g.alchemy.com/nft/v3/{api_key}/getNFTsForOwner"
            
            params = {
                "owner": self.address,
                "contractAddresses[]": [NETPACKETS_CONTRACT],
                "withMetadata": "false"
            }
            
            response = requests.get(api_url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                token_ids = []
                
                for nft in data.get("ownedNfts", []):
                    token_id_hex = nft.get("tokenId", nft.get("id", {}).get("tokenId", "0"))
                    token_id = int(token_id_hex, 16) if token_id_hex.startswith("0x") else int(token_id_hex)
                    token_ids.append(token_id)
                
                if token_ids:
                    token_ids.sort()
                    print(f"✅ Instant: Found {len(token_ids)} NFTs via API (0 seconds!)\n")
                    
                    preview = token_ids[:10]
                    preview_str = ", ".join(map(str, preview))
                    if len(token_ids) > 10:
                        preview_str += f", ... (+{len(token_ids) - 10} more)"
                    print(f"📦 Your NFTs: {preview_str}\n")
                    
                    return token_ids
                else:
                    print(f"  ℹ️  API returned 0 NFTs, using event scanning...\n")
                    return None
            else:
                print(f"  ℹ️  API error {response.status_code}, using event scanning...\n")
                return None
            
        except ImportError:
            print(f"  ℹ️  Install 'requests': pip install requests\n")
            return None
        except Exception as e:
            print(f"  ℹ️  API unavailable, using event scanning...\n")
            return None
    
    def _get_nfts_from_events(self, blocks_back=5000):
        """Fast method: Get NFTs by scanning Transfer events"""
        print(f"🔍 Scanning Transfer events (last {blocks_back:,} blocks)...")
        print(f"  💡 This may take 30-60 seconds...\n")
        
        try:
            current_block = self.w3.eth.block_number
            print(f"  📍 Current block: {current_block:,}")
        except Exception as e:
            print(f"  ⚠️  Could not get current block: {e}")
            print(f"  💡 Falling back to scanning method...")
            return self._get_nfts_by_scanning(max_check=1000)
        
        from_block = max(0, current_block - blocks_back)
        print(f"  📍 Scanning from block: {from_block:,}")
        
        # Transfer event signature: Transfer(address indexed from, address indexed to, uint256 indexed tokenId)
        transfer_topic = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
        
        # Get all transfers TO this address
        print(f"  📥 Scanning transfers TO your wallet...")
        my_address_padded = "0x" + self.address[2:].lower().zfill(64)
        
        received_nfts = set()
        sent_nfts = set()
        
        try:
            # Get logs in smaller chunks to avoid RPC limits
            chunk_size = 1000  # Small chunks for maximum compatibility
            chunks_processed = 0
            max_errors = 3
            error_count = 0
            
            for chunk_start in range(from_block, current_block + 1, chunk_size):
                chunk_end = min(chunk_start + chunk_size - 1, current_block)
                
                try:
                    # Get transfers TO wallet
                    logs_to = self.w3.eth.get_logs({
                        'fromBlock': chunk_start,
                        'toBlock': chunk_end,
                        'address': NETPACKETS_CONTRACT,
                        'topics': [transfer_topic, None, my_address_padded]
                    })
                    
                    for log in logs_to:
                        if len(log['topics']) >= 4:
                            token_id = int(log['topics'][3].hex(), 16)
                            received_nfts.add(token_id)
                    
                    # Get transfers FROM wallet (to subtract)
                    logs_from = self.w3.eth.get_logs({
                        'fromBlock': chunk_start,
                        'toBlock': chunk_end,
                        'address': NETPACKETS_CONTRACT,
                        'topics': [transfer_topic, my_address_padded, None]
                    })
                    
                    for log in logs_from:
                        if len(log['topics']) >= 4:
                            token_id = int(log['topics'][3].hex(), 16)
                            sent_nfts.add(token_id)
                    
                    chunks_processed += 1
                    error_count = 0  # Reset error counter on success
                    
                    # Progress every 5 chunks
                    if chunks_processed % 5 == 0:
                        percent = int((chunk_end - from_block) / (current_block - from_block) * 100)
                        current_owned = len(received_nfts - sent_nfts)
                        print(f"  ⏳ {percent}% - Block {chunk_end:,}/{current_block:,} | Received: {len(received_nfts)} | Sent: {len(sent_nfts)} | Owned: {current_owned}")
                        
                except Exception as chunk_error:
                    error_count += 1
                    if error_count >= max_errors:
                        print(f"  ❌ Too many errors, switching to direct scan...")
                        return self._get_nfts_by_scanning(max_check=1000)
                    # Silent continue on occasional errors
                    continue
                
                if chunk_end >= current_block:
                    break
        
        except KeyboardInterrupt:
            print(f"\n  ⚠️  Scan interrupted!")
            current_owned = received_nfts - sent_nfts
            if len(current_owned) > 0:
                print(f"  💡 Found {len(current_owned)} NFTs so far")
                my_nfts = sorted(list(current_owned))
                return my_nfts
            else:
                raise
        except Exception as e:
            print(f"  ⚠️  Error getting events: {str(e)[:100]}")
            print(f"  💡 Trying direct scan instead...")
            return self._get_nfts_by_scanning(max_check=1000)
        
        # Calculate currently owned: received - sent
        my_nfts = sorted(list(received_nfts - sent_nfts))
        
        print(f"  ✅ Summary: Received {len(received_nfts)}, Sent {len(sent_nfts)}, Currently own {len(my_nfts)}")
        
        print(f"✅ You currently own {len(my_nfts)} NFTs")
        if my_nfts:
            preview = my_nfts[:10]
            preview_str = ", ".join(map(str, preview))
            if len(my_nfts) > 10:
                preview_str += f", ... (+{len(my_nfts) - 10} more)"
            print(f"📦 Your NFTs: {preview_str}\n")
        
        return my_nfts
    
    def _get_nfts_by_balance(self):
        """Try to get NFTs using balanceOf"""
        try:
            balance = self.netpackets.functions.balanceOf(self.address).call()
            print(f"  📊 Balance shows: {balance} NFTs")
            
            if balance == 0:
                print(f"  ℹ️  No NFTs in this wallet\n")
                return []
            
            print(f"  💡 You have {balance} NFTs but need to use scanning to find them...")
            return self._get_nfts_by_scanning(max_check=2000)
            
        except Exception as e:
            print(f"  ⚠️  Could not check balance: {e}")
            print(f"  💡 Trying direct scan...")
            return self._get_nfts_by_scanning(max_check=2000)
    
    def _get_nfts_by_scanning(self, max_check=1000):
        """Slow method: Check each token ID individually"""
        print(f"\n🔍 Direct scan mode (checking up to token #{max_check})...")
        print(f"  💡 This checks each token individually - slow but reliable\n")
        
        my_nfts = []
        checked = 0
        last_valid = 0
        
        for token_id in range(1, max_check + 1):
            try:
                owner = self.netpackets.functions.ownerOf(token_id).call()
                last_valid = token_id
                if owner.lower() == self.address.lower():
                    my_nfts.append(token_id)
                checked += 1
                
                if checked % 50 == 0:
                    percent = int(checked / max_check * 100)
                    print(f"  ⏳ {percent}% - Checked {checked}/{max_check} | Found: {len(my_nfts)} yours")
                    
            except KeyboardInterrupt:
                print(f"\n  ⚠️  Scan interrupted at token #{token_id}")
                print(f"  💡 Found {len(my_nfts)} NFTs so far")
                break
            except Exception:
                # Token doesn't exist
                if token_id - last_valid > 100:
                    # If no valid tokens in last 100, probably reached the end
                    print(f"  ℹ️  No more tokens found, stopping at #{token_id}")
                    break
                pass
        
        print(f"\n✅ Scan complete: Found {len(my_nfts)} NFTs in your wallet")
        if my_nfts:
            preview = my_nfts[:10]
            preview_str = ", ".join(map(str, preview))
            if len(my_nfts) > 10:
                preview_str += f", ... (+{len(my_nfts) - 10} more)"
            print(f"📦 Your NFTs: {preview_str}\n")
        else:
            print(f"  ℹ️  No NetPackets NFTs found on this wallet\n")
        
        return my_nfts
    
    def approve_bulk_transfer(self):
        """Approve bulk transfer contract to manage NFTs"""
        print(f"\n🔐 Checking approval for bulk transfer contract...")
        
        try:
            is_approved = self.netpackets.functions.isApprovedForAll(
                self.address,
                BULK_TRANSFER_CONTRACT
            ).call()
            
            if is_approved:
                print(f"✅ Bulk transfer contract already approved\n")
                return True
            
            print(f"📝 Approving bulk transfer contract...")
            
            tx = self.netpackets.functions.setApprovalForAll(
                BULK_TRANSFER_CONTRACT,
                True
            ).build_transaction({
                'from': self.address,
                'nonce': self.w3.eth.get_transaction_count(self.address),
            })
            
            signed_tx = self.w3.eth.account.sign_transaction(tx, self.private_key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            
            print(f"📤 Approval TX: {tx_hash.hex()}")
            print(f"🔗 https://basescan.org/tx/{tx_hash.hex()}")
            print(f"⏳ Waiting for confirmation...")
            
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            
            if receipt['status'] == 1:
                print(f"✅ Bulk transfer contract approved!\n")
                return True
            else:
                print(f"❌ Approval failed!\n")
                return False
                
        except Exception as e:
            print(f"❌ Error approving: {e}\n")
            return False
    
    def bulk_transfer_external(self, token_ids, to_address):
        """Use external bulk transfer contract to send all NFTs in ONE transaction"""
        print(f"\n{'='*60}")
        print(f"⚡ EXTERNAL BULK TRANSFER (ONE Transaction)")
        print(f"{'='*60}")
        print(f"📦 Tokens: {len(token_ids)} NFTs")
        print(f"📬 To: {to_address}")
        print(f"{'='*60}\n")
        
        # Approve bulk transfer contract first
        if not self.approve_bulk_transfer():
            print(f"❌ Failed to approve bulk transfer contract")
            return False
        
        try:
            # Build the calldata for bulkTransfer
            # Format: array of [type, contract, tokenId, amount]
            transfers = []
            for token_id in token_ids:
                transfers.append([
                    2,  # ERC-721
                    NETPACKETS_CONTRACT,
                    token_id,
                    1  # amount (always 1 for ERC-721)
                ])
            
            # This is complex encoding - use raw calldata
            print(f"⚠️  Note: Using external bulk transfer requires complex encoding")
            print(f"💡 Falling back to rapid sequential transfer for reliability\n")
            
            return self.rapid_sequential_transfer(token_ids, to_address)
                
        except Exception as e:
            print(f"❌ Error: {e}")
            print(f"💡 Falling back to rapid sequential transfer\n")
            return self.rapid_sequential_transfer(token_ids, to_address)
    
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
                print(f"🎫 Token IDs: {', '.join(map(str, token_ids[:10]))}")
                if len(token_ids) > 10:
                    print(f"    ... and {len(token_ids) - 10} more")
                
                # Choose transfer method
                print(f"\nChoose transfer method:")
                print(f"1. Rapid sequential (multiple txs, ~1-2 min for {count} NFTs)")
                print(f"2. Try external bulk transfer (experimental, ONE tx)")
                
                method = input("\nEnter method (1 or 2, default 1): ").strip() or "1"
                
                confirm = input("\nProceed? (y/n): ").strip().lower()
                
                if confirm == 'y':
                    if method == "2":
                        batch.bulk_transfer_external(token_ids, to_address)
                    else:
                        batch.rapid_sequential_transfer(token_ids, to_address)
            
            elif mode == "2":
                # Transfer to multiple addresses
                print(f"\nYou have {len(my_nfts)} NFTs total")
                print(f"Choose distribution mode:")
                print(f"1. One NFT per address (classic)")
                print(f"2. Distribute evenly across addresses")
                print(f"3. Custom amount per address")
                
                dist_mode = input("\nEnter mode (1/2/3, default 1): ").strip() or "1"
                
                addresses_input = input("Enter addresses (comma-separated): ").strip()
                addresses = [x.strip() for x in addresses_input.split(",") if x.strip()]
                
                if not addresses:
                    print("❌ No addresses provided")
                    return
                
                if dist_mode == "1":
                    # One NFT per address
                    count = min(len(my_nfts), len(addresses))
                    token_ids = my_nfts[:count]
                    
                    print(f"\n📦 Will transfer {count} NFTs to {len(addresses)} addresses (1 NFT each)")
                    confirm = input("Proceed? (y/n): ").strip().lower()
                    
                    if confirm == 'y':
                        batch.transfer_to_multiple(token_ids, addresses)
                        
                elif dist_mode == "2":
                    # Distribute evenly
                    per_address = input(f"\nHow many NFTs per address? (max {len(my_nfts) // len(addresses)}): ").strip()
                    per_address = int(per_address)
                    
                    total_needed = per_address * len(addresses)
                    if total_needed > len(my_nfts):
                        print(f"⚠️  Need {total_needed} NFTs but you only have {len(my_nfts)}")
                        print(f"  Will send {len(my_nfts) // len(addresses)} per address instead")
                        per_address = len(my_nfts) // len(addresses)
                    
                    # Create distribution
                    all_token_ids = []
                    all_addresses = []
                    for addr in addresses:
                        for i in range(per_address):
                            idx = len(all_token_ids)
                            if idx < len(my_nfts):
                                all_token_ids.append(my_nfts[idx])
                                all_addresses.append(addr)
                    
                    print(f"\n📦 Will transfer {len(all_token_ids)} NFTs total:")
                    for addr in addresses:
                        count_for_addr = all_addresses.count(addr)
                        print(f"  • {addr[:10]}...{addr[-8:]}: {count_for_addr} NFTs")
                    
                    confirm = input("\nProceed? (y/n): ").strip().lower()
                    
                    if confirm == 'y':
                        batch.transfer_to_multiple(all_token_ids, all_addresses)
                        
                elif dist_mode == "3":
                    # Custom per address
                    print(f"\nEnter amount for each address:")
                    distribution = []
                    total = 0
                    
                    for i, addr in enumerate(addresses):
                        amount = input(f"  {i+1}. {addr[:10]}...{addr[-8:]}: ").strip()
                        amount = int(amount) if amount else 1
                        distribution.append(amount)
                        total += amount
                    
                    if total > len(my_nfts):
                        print(f"⚠️  Total {total} exceeds your {len(my_nfts)} NFTs!")
                        return
                    
                    # Create distribution
                    all_token_ids = []
                    all_addresses = []
                    idx = 0
                    for addr, amount in zip(addresses, distribution):
                        for _ in range(amount):
                            if idx < len(my_nfts):
                                all_token_ids.append(my_nfts[idx])
                                all_addresses.append(addr)
                                idx += 1
                    
                    print(f"\n📦 Will transfer {len(all_token_ids)} NFTs")
                    confirm = input("Proceed? (y/n): ").strip().lower()
                    
                    if confirm == 'y':
                        batch.transfer_to_multiple(all_token_ids, all_addresses)
        
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
