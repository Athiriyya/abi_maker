#! /usr/bin/env python

import traceback

import web3
from web3 import Web3
from web3.datastructures import AttributeDict
from web3.middleware import geth_poa_middleware

from .credentials import Credentials
from .solidity_types import *

from typing import Dict, Tuple, Union


DEFAULT_RPC = '<<DEFAULT_RPC>>'
DEFAULT_TIMEOUT = 30

class ABIWrapperContract:
    def __init__(self, 
                 contract_address:address, 
                 abi:str, 
                 rpc:str=None):
        self.rpc = rpc or DEFAULT_RPC
        # FIXME: when used by many contracts, this creates many identical w3 
        # instances, when only one is required, or when they could be lazily 
        # created. Combine or cache them?
        self.w3 = Web3(Web3.HTTPProvider(self.rpc))
        self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)

        self.abi = abi
        self.contract_address = contract_address
        self.contract = self.w3.eth.contract(self.contract_address, abi=abi)

        # FIXME: self.get_dynamic_gas_fee() requires a network call and can be slow
        # self.gas_price, self.gas = self.get_dynamic_gas_fee()
        self.gas_price, self.gas = (0, 0)

        self.timeout = DEFAULT_TIMEOUT
        self.nonce = 0

    def fetch_nonce(self, address:address) -> int:
        nonce = self.w3.eth.getTransactionCount( address, 'pending')
        return nonce        

    def call_contract_function(self, function_name:str, *args):
        contract_func = getattr(self.contract, function_name)
        return contract_func(*args).call()

    def send_transaction(self,
                         tx,
                         cred:Credentials,
                         wait_result=True,
                         nonce=None,
                         retry_on_low_nonce=True
                        ) -> Union[TxReceipt, str]:
        # We keep track of our own nonce, and only re-fetch it if a 'nonce too low'
        # error gets thrown
        if nonce is None:
            nonce = self.nonce
            self.nonce += 1
            
        # TODO: how often should we update the gas fee? For the moment, we do 
        # it every time, but it's an extra blockchain access for every transaction,
        self.gas_price, self.gas = self.get_dynamic_gas_fee()
        tx = tx.buildTransaction( { 'gas': self.gas, 'gasPrice': self.gas_price, 'nonce': nonce})        
        signed_tx = self.w3.eth.account.sign_transaction(tx, private_key=cred.private_key)
        try:
            self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)

        except Exception as e:
            if 'nonce too low' in str(e):
                if retry_on_low_nonce:
                    self.nonce = self.fetch_nonce(cred.address)
                    return self.send_transaction( tx, cred, wait_result=wait_result )

            traceback.print_exc()
            return None

        if wait_result:
            receipt = self.w3.eth.wait_for_transaction_receipt(
                transaction_hash=signed_tx.hash,
                poll_latency=1,
                timeout=self.timeout,
            )
            return receipt
        else:
            return signed_tx.hash.hex()

    def get_dynamic_gas_fee(self) ->Tuple[int, int]:
        block = self.w3.eth.getBlock("pending")
        base_gas = block.gasUsed + self.w3.toWei(50, 'gwei')
        gas_limit =block.gasLimit

        return base_gas, gas_limit

    def tx_receipt_for_hash(self, tx_hash:address) -> TxReceipt:
        tx_receipt = self.w3.eth.get_transaction_receipt(tx_hash)
        return tx_receipt

    def parse_events(self, tx_receipt:TxReceipt) -> Dict[str, AttributeDict]:
        event_dicts = {}
        for event in self.contract.events:
            eds = event().processReceipt(tx_receipt, errors=web3.logs.DISCARD)
            if eds:
                for ed in eds:
                    event_dicts.setdefault(ed.event,[]).append(ed)
        return event_dicts        
