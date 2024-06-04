from algopy import ARC4Contract, Asset, Global, Txn, UInt64, arc4, gtxn, itxn, op


class DigitalMarketplace(ARC4Contract):

    # Recibir o permitir assets de venta
    @arc4.abimethod
    def allow_asset(self, mbr_pay: gtxn.PaymentTransaction, asset: Asset) -> None:
        # Verificar que el contrato no haya hecho optin antes al asset
        assert not Global.current_application_address.is_opted_in(asset)

        # Verificar la transacción del MBR
        assert mbr_pay.receiver == Global.current_application_address
        assert mbr_pay.amount == Global.asset_opt_in_min_balance

        # Hacer el optin del contrato al asset
        itxn.AssetTransfer(
            xfer_asset=asset,
            asset_receiver=Global.current_application_address,
            asset_amount=0,
            fee=0,
        ).submit()

    # Depositar assets en el contrato
    @arc4.abimethod
    def first_deposit(
        self,
        mbr_pay: gtxn.PaymentTransaction,
        xfer: gtxn.AssetTransferTransaction,
        unitary_price: arc4.UInt64,
    ) -> None:
        # Box: Key -> Value  // [address,asset_id] -> [quantity, price]
        # Boxes MBR -> 0.0025 por Box + 0.0004 por cada byte
        # MBR del caso de uso -> [32 Bytes, 8 Bytes] -> [8 Bytes, 8 Bytes] = 56 Bytes
        # MBR del caso = 0.0025 + 0.0004*56

        assert mbr_pay.sender == Txn.sender
        assert mbr_pay.receiver == Global.current_application_address
        assert mbr_pay.amount == UInt64(2_500 + 400 * 56)

        box_key = Txn.sender.bytes + op.itob(xfer.xfer_asset.id)
        _length, exists = op.Box.length(box_key)
        assert not exists

        assert xfer.asset_receiver == Global.current_application_address
        assert xfer.sender == Txn.sender
        assert xfer.asset_amount > 0

        op.Box.put(box_key, op.itob(xfer.asset_amount) + unitary_price.bytes)

    @arc4.abimethod
    def deposit(
        self,
        xfer: gtxn.AssetTransferTransaction,
    ) -> None:
        box_key = Txn.sender.bytes + op.itob(xfer.xfer_asset.id)
        _length, exists = op.Box.length(box_key)
        assert exists

        assert xfer.asset_receiver == Global.current_application_address
        assert xfer.sender == Txn.sender
        assert xfer.asset_amount > 0

        current_deposited = op.btoi(op.Box.extract(box_key, 0, 8))
        op.Box.replace(box_key, 0, op.itob(current_deposited + xfer.asset_amount))

    # Funcion de modificar o definir el precio de venta
    @arc4.abimethod
    def set_price(
        self,
        unitary_price: arc4.UInt64,
        asset: Asset,
    ) -> None:
        box_key = Txn.sender.bytes + op.itob(asset.id)

        op.Box.replace(box_key, 8, unitary_price.bytes)

    # Retirar sus ganancias y assets restantes
    @arc4.abimethod
    def withdraw(
        self,
        asset: Asset,
    ) -> None:
        box_key = Txn.sender.bytes + op.itob(asset.id)
        current_deposited = op.btoi(op.Box.extract(box_key, 0, 8))
        op.Box.delete(box_key)

        itxn.AssetTransfer(
            xfer_asset=asset,
            asset_amount=current_deposited,
            asset_receiver=Txn.sender,
            fee=0,
        ).submit()

        itxn.Payment(
            receiver=Txn.sender,
            amount=UInt64(2_500 + 400 * 56),
            fee=0,
        ).submit()

    # Funcion de compra de assets
    @arc4.abimethod
    def buy(
        self,
        owner: arc4.Address,
        asset: Asset,
        buy_pay: gtxn.PaymentTransaction,
        amount: UInt64,
    ) -> None:
        box_key = owner.bytes + op.itob(asset.id)
        unitary_price = op.btoi(op.Box.extract(box_key, 8, 8))

        assert buy_pay.receiver == Global.current_application_address
        assert buy_pay.sender == Txn.sender
        assert buy_pay.amount == unitary_price * amount

        current_deposited = op.btoi(op.Box.extract(box_key, 0, 8))
        op.Box.replace(box_key, 0, op.itob(current_deposited - amount))

        itxn.AssetTransfer(
            xfer_asset=asset,
            asset_receiver=Txn.sender,
            asset_amount=amount,
            fee=0,
        ).submit()
