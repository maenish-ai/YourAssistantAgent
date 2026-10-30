"""Crisp QR modules, shared by the UI and cross-language scanner regression."""
def pairing_qr_image(payload,max_pixels=300):
    import qrcode
    code=qrcode.QRCode(box_size=5,border=4)
    code.add_data(payload);code.make(fit=True)
    modules=code.modules_count+8
    code.box_size=max(2,min(6,max_pixels//modules))
    return code.make_image(fill_color='black',back_color='white').convert('RGB')
