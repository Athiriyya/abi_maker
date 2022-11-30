#! /usr/bin/env python

import traceback

import web3
from web3 import Web3
from web3.datastructures import AttributeDict
from web3.middleware import geth_poa_middleware

from .credentials import Credentials

from .solidity_types import *
from web3.contract import Contract
from typing import Dict, Tuple, Union, Optional, Any

DEFAULT_TIMEOUT = 30
DEFAULT_MAX_GAS = 50
DEFAULT_MAX_PRIORITY_GAS = 3

W3_INSTANCES: Dict[str, Web3] = {}

class ABIWrapperContract:
    def __init__(self, 
                 contract_address:Optional[address], 
                 abi:str,
                 rpc:str,
                 max_gas_gwei:float=DEFAULT_MAX_GAS,
                 max_priority_gwei:float=DEFAULT_MAX_PRIORITY_GAS):
        self.rpc = rpc
        self.contract_address = contract_address
        self.abi = abi
        self.contract = None
        self.nonces: Dict[address, int] = {}
        self.timeout = DEFAULT_TIMEOUT

        # This one superclass may be used by many contracts, who don't all need to
        # create separate Web3 instances. Just use one per RPC
        global W3_INSTANCES
        w3 = W3_INSTANCES.get(self.rpc, None)
        if not w3:
            w3 = Web3(Web3.HTTPProvider(self.rpc))
            w3.middleware_onion.inject(geth_poa_middleware, layer=0)
            W3_INSTANCES[self.rpc] = w3
        self.w3 = w3

        self.max_gas_wei = self.w3.toWei(max_gas_gwei, 'gwei')
        self.max_priority_wei = self.w3.toWei(max_priority_gwei, 'gwei')

        if self.contract_address:
            self.contract = self.w3.eth.contract(self.contract_address, abi=self.abi)

    def get_nonce_and_update(self, address:address, force_fetch=False) -> int:
        # We keep track of our own nonce, and only re-fetch it if a 'nonce too low'
        # error gets thrown       
        nonce = self.nonces.get(address, 0) 
        if force_fetch or nonce == 0:
            nonce = self.w3.eth.getTransactionCount( address, 'pending')

        # Store the next nonce this address will use, and return the current one
        self.nonces[address] = nonce + 1
        return nonce

    def get_gas_dict_and_update(self, address:address) -> Dict[str, float]:
        nonce = self.get_nonce_and_update(address)
         
        legacy = False
        if legacy:
            # TODO: it's expensive to query for fees with every transaction. 
            # Maybe query only once a minute?
            gas, gas_price = self.get_legacy_gas_fee()
            gas_dict = {'gas': gas, 'gasPrice':gas_price, 'nonce':nonce}
        else:
            gas_dict = {
                'from': address, 
                'maxFeePerGas': self.max_gas_wei, 
                'maxPriorityFeePerGas': self.max_priority_wei, 
                'nonce': nonce
            }
        return gas_dict

    def call_contract_function(self, function_name:str, *args) -> Any:
        contract_func = getattr(self.contract, function_name)
        return contract_func(*args).call()

    def get_custom_contract(self, contract_address:address, abi:str=None) -> Contract:
        # TODO: Many custom contracts for e.g. ERC20 tokens could
        # be re-used by caching a contracts dictionary keyed by address
        # For now, just return a new contract
        abi = abi or self.abi
        contract = self.w3.eth.contract(contract_address, abi=abi)
        return contract

    def send_transaction(self,
                         tx,
                         cred:Credentials,
                         nonce=None
                        ) -> Optional[TxReceipt]:

        address = cred.address  
        gas_dict = self.get_gas_dict_and_update(address)
        tx_dict = tx.buildTransaction(gas_dict)    
        signed_tx = self.w3.eth.account.sign_transaction(tx_dict, private_key=cred.private_key)
        try:
            self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)

        except Exception as e:
            if 'nonce too low' in str(e):
                nonce = self.get_nonce_and_update(address, force_fetch=True)
                return self.send_transaction( tx, cred)

            traceback.print_exc()
            return None

        receipt = self.w3.eth.wait_for_transaction_receipt(
            transaction_hash=signed_tx.hash,
            poll_latency=1,
            timeout=self.timeout,
        )
        return receipt

    def get_legacy_gas_fee(self) ->Tuple[int, int]:
        # See: https://web3py.readthedocs.io/en/stable/gas_price.html#gas-price-api
        # Some transactions may require a gas dict with the keys {'gasPrice': x_wei, '': y_wei}
        block = self.w3.eth.getBlock("pending")
        base_gas = block.gasUsed + self.w3.toWei(50, 'gwei')
        gas_limit =block.gasLimit

        return base_gas, gas_limit

    def tx_receipt_for_hash(self, tx_hash:address) -> TxReceipt:
        tx_receipt = self.w3.eth.get_transaction_receipt(tx_hash)
        return tx_receipt

    def parse_events(self, tx_receipt:TxReceipt, names:Sequence[str]=None) -> Dict[str, AttributeDict]:
        event_dicts = {}
        for event in self.contract.events:
            eds = event().processReceipt(tx_receipt, errors=web3.logs.DISCARD)
            if eds:
                for ed in eds:
                    event_dicts.setdefault(ed.event,[]).append(ed)
        if names:
            event_dicts = {k:v for k,v in event_dicts.items() if k in names}
        return event_dicts        
