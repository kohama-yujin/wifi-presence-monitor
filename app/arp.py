from scapy.all import ARP, Ether, srp

from app.config import ARP_TIMEOUT_SECONDS, normalize_mac


def arp_request(ip: str) -> str | None:
    """ARPを送信して、指定したIPのMACアドレスを取得する。取得できない場合はNoneを返す。"""
    packet = Ether(dst="ff:ff:ff:ff:ff:ff") / ARP(pdst=ip)
    answered, _ = srp(packet, timeout=ARP_TIMEOUT_SECONDS, verbose=False)
    if answered:
        return normalize_mac(answered[0][1].hwsrc)
    return None
