import base64

import algokit_utils
import algosdk
import pytest
from algokit_utils.beta.account_manager import AddressAndSigner
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


@pytest.fixture(scope="session")
def algorand() -> AlgorandClient:
    client = AlgorandClient.default_local_net()
    client.set_default_validity_window(1000)
    return client


@pytest.fixture(scope="session")
def dispenser(algorand: AlgorandClient) -> AddressAndSigner:
    return algorand.account.dispenser()


@pytest.fixture(scope="session")
def creator(algorand: AlgorandClient, dispenser: AddressAndSigner) -> AddressAndSigner:
    acct = algorand.account.random()

    algorand.send.payment(
        PayParams(sender=dispenser.address, receiver=acct.address, amount=10_000_000)
    )

    return acct


@pytest.fixture(scope="session")
def test_assets_id(
    creator: AddressAndSigner,
    algorand: AlgorandClient,
) -> (int, int):
    asset1_id = algorand.send.asset_create(
        AssetCreateParams(sender=creator.address, total=10, decimals=0)
    )["confirmation"]["asset-index"]
    asset2_id = algorand.send.asset_create(
        AssetCreateParams(sender=creator.address, total=20, decimals=0)
    )["confirmation"]["asset-index"]

    return (asset1_id, asset2_id)


@pytest.fixture(scope="session")
def digital_marketplace_client(
    creator: AddressAndSigner,
    algorand: AlgorandClient,
) -> DigitalMarketplaceClient:
    client = DigitalMarketplaceClient(
        algorand.client.algod,
        sender=creator.address,
        signer=creator.signer,
    )

    client.create_bare()

    return client


@pytest.fixture(scope="session")
def buyer(
    algorand: AlgorandClient, dispenser: AddressAndSigner, test_assets_id: (int, int)
) -> AddressAndSigner:
    acct = algorand.account.random()
    algorand.send.payment(
        PayParams(sender=dispenser.address, receiver=acct.address, amount=20_000_000)
    )

    for asset_id in test_assets_id:
        algorand.send.asset_transfer(
            AssetTransferParams(
                asset_id=asset_id, sender=acct.address, receiver=acct.address, amount=0
            )
        )
    return acct


def test_allow_asset(
    algorand: AlgorandClient,
    digital_marketplace_client: DigitalMarketplaceClient,
    creator: AddressAndSigner,
    dispenser: AddressAndSigner,
    test_assets_id: (int, int),
) -> None:

    algorand.send.payment(
        PayParams(
            sender=dispenser.address,
            receiver=digital_marketplace_client.app_address,
            amount=100_000,
        )
    )

    digital_marketplace_client.allow_asset(
        mbr_pay=TransactionWithSigner(
            algorand.transactions.payment(
                PayParams(
                    sender=creator.address,
                    receiver=digital_marketplace_client.app_address,
                    amount=100_000,
                    extra_fee=1_000,
                )
            ),
            signer=creator.signer,
        ),
        asset=test_assets_id[0],
    )

    digital_marketplace_client.allow_asset(
        mbr_pay=TransactionWithSigner(
            algorand.transactions.payment(
                PayParams(
                    sender=creator.address,
                    receiver=digital_marketplace_client.app_address,
                    amount=100_000,
                    extra_fee=1_000,
                )
            ),
            signer=creator.signer,
        ),
        asset=test_assets_id[1],
    )

    assert (
        digital_marketplace_client.algod_client.account_asset_info(
            digital_marketplace_client.app_address, test_assets_id[0]
        )["asset-holding"]["amount"]
        == 0
    )

    assert (
        digital_marketplace_client.algod_client.account_asset_info(
            digital_marketplace_client.app_address, test_assets_id[1]
        )["asset-holding"]["amount"]
        == 0
    )


def test_first_deposit(
    algorand: AlgorandClient,
    creator: AddressAndSigner,
    test_assets_id: (int, int),
    digital_marketplace_client: DigitalMarketplaceClient,
) -> None:
    for asset_id in test_assets_id:
        box_key = algosdk.encoding.decode_address(
            creator.address
        ) + algosdk.encoding.encode_as_bytes(asset_id)
        result = digital_marketplace_client.first_deposit(
            mbr_pay=TransactionWithSigner(
                algorand.transactions.payment(
                    PayParams(
                        sender=creator.address,
                        receiver=digital_marketplace_client.app_address,
                        amount=(2_500 + 400 * 56),
                    )
                ),
                signer=creator.signer,
            ),
            xfer=TransactionWithSigner(
                algorand.transactions.asset_transfer(
                    AssetTransferParams(
                        asset_id=asset_id,
                        sender=creator.address,
                        receiver=digital_marketplace_client.app_address,
                        amount=3,
                    )
                ),
                signer=creator.signer,
            ),
            unitary_price=1_000_000,
            transaction_parameters=algokit_utils.TransactionParameters(
                boxes=[(0, box_key)]
            ),
        )
        assert result.confirmed_round
        box_content = algorand.client.algod.application_box_by_name(
            digital_marketplace_client.app_id,
            box_key,
        )["value"]

        decoded_box_content = base64.b64decode(box_content)
        assert int.from_bytes(decoded_box_content[:8], "big") == 3
        assert int.from_bytes(decoded_box_content[8:16], "big") == 1_000_000


def test_deposit(
    algorand: AlgorandClient,
    creator: AddressAndSigner,
    test_assets_id: (int, int),
    digital_marketplace_client: DigitalMarketplaceClient,
) -> None:
    for asset_id in test_assets_id:
        box_key = algosdk.encoding.decode_address(
            creator.address
        ) + algosdk.encoding.encode_as_bytes(asset_id)
        deposit_result = digital_marketplace_client.deposit(
            xfer=TransactionWithSigner(
                algorand.transactions.asset_transfer(
                    AssetTransferParams(
                        asset_id=asset_id,
                        sender=creator.address,
                        receiver=digital_marketplace_client.app_address,
                        amount=1,
                    )
                ),
                creator.signer,
            ),
            transaction_parameters=algokit_utils.TransactionParameters(
                boxes=[(0, box_key)]
            ),
        )
        assert deposit_result.confirmed_round

        box_content = algorand.client.algod.application_box_by_name(
            digital_marketplace_client.app_id,
            box_key,
        )["value"]

        decoded_box_content = base64.b64decode(box_content)
        assert int.from_bytes(decoded_box_content[:8], "big") == 4


def set_price(
    algorand: AlgorandClient,
    creator: AddressAndSigner,
    test_assets_id: (int, int),
    digital_marketplace_client: DigitalMarketplaceClient,
) -> None:
    for asset_id, unitary_price in zip(test_assets_id, [3_000_000, 2_000_000]):
        box_key = algosdk.encoding.decode_address(
            creator.address
        ) + algosdk.encoding.encode_as_bytes(asset_id)
        result = digital_marketplace_client.set_price(
            unitary_price=unitary_price,
            asset=asset_id,
            transaction_parameters=algokit_utils.TransactionParameters(
                boxes=[(0, box_key)]
            ),
        )

        assert result.confirmed_round

        box_content = algorand.client.algod.application_box_by_name(
            digital_marketplace_client.app_id,
            box_key,
        )["value"]

        decoded_box_content = base64.b64decode(box_content)
        assert int.from_bytes(decoded_box_content[8:16], "big") == unitary_price


def test_buy(
    algorand: AlgorandClient,
    digital_marketplace_client: DigitalMarketplaceClient,
    creator: AddressAndSigner,
    test_assets_id: (int, int),
    buyer: AddressAndSigner,
) -> None:
    for asset_id in test_assets_id:
        quantity = 2
        box_key = algosdk.encoding.decode_address(
            creator.address
        ) + algosdk.encoding.encode_as_bytes(asset_id)

        box_content = algorand.client.algod.application_box_by_name(
            digital_marketplace_client.app_id,
            box_key,
        )["value"]

        decoded_box_content = base64.b64decode(box_content)
        amount_to_pay = int.from_bytes(decoded_box_content[8:16], "big") * quantity

        result = digital_marketplace_client.buy(
            owner=creator.address,
            asset=asset_id,
            buy_pay=TransactionWithSigner(
                algorand.transactions.payment(
                    PayParams(
                        sender=buyer.address,
                        receiver=digital_marketplace_client.app_address,
                        amount=amount_to_pay,
                        extra_fee=1_000,
                    )
                ),
                signer=buyer.signer,
            ),
            amount=2,
            transaction_parameters=algokit_utils.TransactionParameters(
                sender=buyer.address, signer=buyer.signer, boxes=[(0, box_key)]
            ),
        )
        assert result.confirmed_round

        assert (
            algorand.client.algod.account_asset_info(buyer.address, asset_id)[
                "asset-holding"
            ]["amount"]
            == quantity
        )


def test_withdraw(
    algorand: AlgorandClient,
    digital_marketplace_client: DigitalMarketplaceClient,
    creator: AddressAndSigner,
    test_assets_id: (int, int),
) -> None:
    for asset_id in test_assets_id:
        box_key = algosdk.encoding.decode_address(
            creator.address
        ) + algosdk.encoding.encode_as_bytes(asset_id)

        box_content = algorand.client.algod.application_box_by_name(
            digital_marketplace_client.app_id,
            box_key,
        )["value"]

        decoded_box_content = base64.b64decode(box_content)
        assets_in_contract = int.from_bytes(decoded_box_content[:8], "big")

        assets_balance_before = algorand.client.algod.account_asset_info(
            creator.address, asset_id
        )["asset-holding"]["amount"]

        algo_balance_before = algorand.client.algod.account_info(creator.address)[
            "amount"
        ]

        box_key = algosdk.encoding.decode_address(
            creator.address
        ) + algosdk.encoding.encode_as_bytes(asset_id)

        sp = algorand.client.algod.suggested_params()
        sp.flat_fee = True
        sp.fee = 4_000

        result = digital_marketplace_client.withdraw(
            asset=asset_id,
            transaction_parameters=algokit_utils.TransactionParameters(
                boxes=[(0, box_key)], suggested_params=sp
            ),
        )

        assert result.confirmed_round

        algo_balance_after = algorand.client.algod.account_info(creator.address)[
            "amount"
        ]
        assert algo_balance_after - algo_balance_before == (2_500 + 400 * 56) - 4_000
        assets_balance_after = algorand.client.algod.account_asset_info(
            creator.address, asset_id
        )["asset-holding"]["amount"]
        assert algorand.client.algod.account_asset_info(creator.address, asset_id)[
            "asset-holding"
        ]["amount"] == (assets_in_contract + assets_balance_before)
