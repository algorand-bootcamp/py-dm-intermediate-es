import base64

import algokit_utils
import algosdk
from algokit_utils.beta.algorand_client import (
    AlgorandClient,
    AssetCreateParams,
    AssetTransferParams,
    PayParams,
)
from algosdk.atomic_transaction_composer import TransactionWithSigner

from smart_contracts.artifacts.digital_marketplace.client import (
    DigitalMarketplaceClient,
)


def start_sale(
    algorand: AlgorandClient,
    digital_marketplace_client: DigitalMarketplaceClient,
    test_asset_id: int,
    sender: str,
    amount: int,
    unitary_price: int,
    app_id: int,
    set_asset_id: callable,
    set_sale_info: callable,
    set_app_id: callable,
) -> None:
    if app_id == 0:
        digital_marketplace_client.create_bare()

    if test_asset_id == 0:
        asset_create_result = algorand.send.asset_create(
            AssetCreateParams(sender=sender, total=10)
        )
        test_asset_id = asset_create_result["confirmation"]["asset-index"]

    # Si el contrato no tiene suficiente saldo, fondearlo
    if (
        algorand.client.algod.account_info(digital_marketplace_client.app_address)[
            "amount"
        ]
        < 100_000
    ):
        algorand.send.payment(
            PayParams(
                sender=sender,
                receiver=digital_marketplace_client.app_address,
                amount=100_000,
            )
        )

    digital_marketplace_client.allow_asset(
        mbr_pay=TransactionWithSigner(
            algorand.transactions.payment(
                PayParams(
                    sender=sender,
                    receiver=digital_marketplace_client.app_address,
                    amount=100_000,
                    extra_fee=1_000,
                )
            ),
        ),
        asset=test_asset_id,
    )

    box_key = algosdk.encoding.decode_address(
        sender
    ) + algosdk.encoding.encode_as_bytes(test_asset_id)

    digital_marketplace_client.first_deposit(
        mbr_pay=algorand.transactions.payment(
            PayParams(
                sender=sender,
                receiver=digital_marketplace_client.app_address,
                amount=(2_500 + 400 * 56),
            )
        ),
        xfer=algorand.transactions.asset_transfer(
            AssetTransferParams(
                asset_id=test_asset_id,
                sender=sender,
                receiver=digital_marketplace_client.app_address,
                amount=amount,
            )
        ),
        unitary_price=unitary_price,
        transaction_parameters=algokit_utils.TransactionParameters(
            boxes=[(0, box_key)]
        ),
    )
    set_asset_id(test_asset_id)
    set_app_id(digital_marketplace_client.app_id)
    set_sale_info(sender, test_asset_id, amount, unitary_price)


def deposit(
    algorand: AlgorandClient,
    digital_marketplace_client: DigitalMarketplaceClient,
    test_asset_id: int,
    sender: str,
    amount: int,
    set_sale_info: callable,
) -> None:
    box_key = algosdk.encoding.decode_address(sender)
    +algosdk.encoding.encode_as_bytes(test_asset_id)

    box_content = algorand.client.algod.application_box_by_name(
        digital_marketplace_client.app_id,
        box_key,
    )["value"]

    decoded_box_content = base64.b64decode(box_content)
    unitary_price = int.from_bytes(decoded_box_content[8:16], "big")
    assets_before_txn = int.from_bytes(decoded_box_content[:8], "big")

    digital_marketplace_client.deposit(
        xfer=algorand.transactions.asset_transfer(
            AssetTransferParams(
                asset_id=test_asset_id,
                sender=sender,
                receiver=digital_marketplace_client.app_address,
                amount=amount,
            )
        ),
        transaction_parameters=algokit_utils.TransactionParameters(
            boxes=[(0, box_key)]
        ),
    )
    set_sale_info(sender, test_asset_id, (amount + assets_before_txn), unitary_price)


def set_price(
    algorand: AlgorandClient,
    digital_marketplace_client: DigitalMarketplaceClient,
    test_asset_id: int,
    sender: str,
    unitary_price: int,
    set_sale_info: callable,
) -> None:
    box_key = algosdk.encoding.decode_address(sender)
    +algosdk.encoding.encode_as_bytes(test_asset_id)

    box_content = algorand.client.algod.application_box_by_name(
        digital_marketplace_client.app_id,
        box_key,
    )["value"]

    decoded_box_content = base64.b64decode(box_content)
    amount = int.from_bytes(decoded_box_content[:8], "big")

    digital_marketplace_client.set_price(
        unitary_price=unitary_price,
        asset=test_asset_id,
        transaction_parameters=algokit_utils.TransactionParameters(
            boxes=[(0, box_key)]
        ),
    )

    set_sale_info(sender, test_asset_id, amount, unitary_price)


def buy(
    algorand: AlgorandClient,
    digital_marketplace_client: DigitalMarketplaceClient,
    test_asset_id: int,
    owner: str,
    buyer: str,
    quantity: int,
    set_sale_info: callable,
) -> None:
    box_key = algosdk.encoding.decode_address(owner)
    +algosdk.encoding.encode_as_bytes(test_asset_id)

    box_content = algorand.client.algod.application_box_by_name(
        digital_marketplace_client.app_id,
        box_key,
    )["value"]

    decoded_box_content = base64.b64decode(box_content)
    amount_to_pay = int.from_bytes(decoded_box_content[8:16], "big") * quantity
    unitary_price = int.from_bytes(decoded_box_content[8:16], "big")
    amount_before_txn = int.from_bytes(decoded_box_content[:8], "big")

    digital_marketplace_client.buy(
        owner=owner,
        asset=test_asset_id,
        buy_pay=algorand.transactions.payment(
            PayParams(
                sender=buyer,
                receiver=digital_marketplace_client.app_address,
                amount=amount_to_pay,
            )
        ),
        amount=quantity,
        transaction_parameters=algokit_utils.TransactionParameters(
            boxes=[(0, box_key)]
        ),
    )

    set_sale_info(owner, test_asset_id, (amount_before_txn - quantity), unitary_price)


def withdraw(
    digital_marketplace_client: DigitalMarketplaceClient,
    test_asset_id: int,
    owner: str,
    set_assets_left: callable,
) -> None:
    box_key = algosdk.encoding.decode_address(owner)
    +algosdk.encoding.encode_as_bytes(test_asset_id)

    digital_marketplace_client.withdraw(
        asset=test_asset_id,
        transaction_parameters=algokit_utils.TransactionParameters(
            boxes=[(0, box_key)]
        ),
    )

    set_assets_left(0)
