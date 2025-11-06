"""
Exemplos de uso dos protocolos implementados.
"""
import sys
import os
import time
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fase1.rdt20 import RDT20Sender, RDT20Receiver
from fase1.rdt30 import RDT30Sender, RDT30Receiver
from fase2.gbn import GBNSender, GBNReceiver
from fase3.tcp_socket import SimpleTCPSocket
from utils.simulator import DirectChannel, UnreliableChannel


def exemplo_rdt20():
    """Exemplo de uso do rdt2.0."""
    print("\n=== Exemplo: rdt2.0 ===")
    
    channel = DirectChannel()
    sender = RDT20Sender(port=5010, dest_port=5011, channel=channel)
    receiver = RDT20Receiver(port=5011, channel=channel)
    
    def receber():
        for _ in range(3):
            msg = receiver.receive(timeout=2)
            if msg:
                print(f"  Recebido: {msg.decode()}")
    
    recv_thread = threading.Thread(target=receber)
    recv_thread.start()
    
    mensagens = ["Olá", "Mundo", "RDT2.0"]
    for msg in mensagens:
        sender.send(msg)
        time.sleep(0.2)
    
    recv_thread.join(timeout=5)
    sender.close()
    receiver.close()


def exemplo_rdt30():
    """Exemplo de uso do rdt3.0 com canal não confiável."""
    print("\n=== Exemplo: rdt3.0 (com perdas) ===")
    
    channel = UnreliableChannel(loss_rate=0.1, corrupt_rate=0.1)
    sender = RDT30Sender(port=5030, dest_port=5031, channel=channel)
    receiver = RDT30Receiver(port=5031, channel=channel)
    
    def receber():
        for _ in range(3):
            msg = receiver.receive(timeout=5)
            if msg:
                print(f"  Recebido: {msg.decode()}")
    
    recv_thread = threading.Thread(target=receber)
    recv_thread.start()
    
    mensagens = ["Teste", "RDT3.0", "Com Perdas"]
    for msg in mensagens:
        sender.send(msg)
        time.sleep(0.3)
    
    recv_thread.join(timeout=10)
    
    stats = sender.get_stats()
    print(f"  Retransmissões: {stats['retransmissions']}")
    print(f"  Throughput: {stats['throughput_mbps']:.4f} Mbps")
    
    sender.close()
    receiver.close()


def exemplo_gbn():
    """Exemplo de uso do Go-Back-N."""
    print("\n=== Exemplo: Go-Back-N ===")
    
    channel = DirectChannel()
    sender = GBNSender(port=6010, dest_port=6011, channel=channel, window_size=5)
    receiver = GBNReceiver(port=6011, channel=channel)
    
    def receber():
        for _ in range(5):
            msg = receiver.receive(timeout=2)
            if msg:
                print(f"  Recebido: {msg.decode()}")
    
    recv_thread = threading.Thread(target=receber)
    recv_thread.start()
    
    for i in range(5):
        sender.send(f"Mensagem {i}".encode())
        time.sleep(0.1)
    
    sender.wait_for_all_acks()
    recv_thread.join(timeout=5)
    
    stats = sender.get_stats()
    print(f"  Throughput: {stats['throughput_mbps']:.4f} Mbps")
    
    sender.close()
    receiver.close()


def exemplo_tcp():
    """Exemplo de uso do TCP simplificado."""
    print("\n=== Exemplo: TCP Simplificado ===")
    
    server = SimpleTCPSocket(8010)
    server.listen()
    
    def servidor():
        conn = server.accept()
        data = conn.recv(1024)
        print(f"  Servidor recebeu: {data.decode()}")
        conn.close()
    
    server_thread = threading.Thread(target=servidor)
    server_thread.start()
    
    time.sleep(0.2)
    
    client = SimpleTCPSocket(9010)
    client.connect(('localhost', 8010))
    
    client.send(b"Hello TCP!")
    time.sleep(1)
    
    stats = client.get_stats()
    print(f"  Bytes enviados: {stats['bytes_sent']}")
    
    client.close()
    server.close()
    time.sleep(0.5)


if __name__ == '__main__':
    print("=" * 60)
    print("EXEMPLOS DE USO DOS PROTOCOLOS")
    print("=" * 60)
    
    try:
        exemplo_rdt20()
        exemplo_rdt30()
        exemplo_gbn()
        exemplo_tcp()
        
        print("\n" + "=" * 60)
        print("Todos os exemplos executados!")
        print("=" * 60)
    except Exception as e:
        print(f"\nErro ao executar exemplos: {e}")
        import traceback
        traceback.print_exc()

