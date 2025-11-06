"""
Testes automatizados para Fase 1 - Protocolos RDT.
"""
import sys
import os
import time
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fase1.rdt20 import RDT20Sender, RDT20Receiver
from fase1.rdt21 import RDT21Sender, RDT21Receiver
from fase1.rdt30 import RDT30Sender, RDT30Receiver
from utils.simulator import UnreliableChannel, DirectChannel


def test_rdt20_perfect_channel():
    """Teste rdt2.0 com canal perfeito."""
    print("\n=== Teste rdt2.0 - Canal Perfeito ===")
    
    channel = DirectChannel()
    sender = RDT20Sender(port=5010, dest_port=5011, channel=channel)
    receiver = RDT20Receiver(port=5011, channel=channel)
    
    # Thread para receber mensagens
    received_messages = []
    def receive_loop():
        for _ in range(10):
            msg = receiver.receive(timeout=2)
            if msg:
                received_messages.append(msg)
    
    recv_thread = threading.Thread(target=receive_loop)
    recv_thread.start()
    
    # Enviar 10 mensagens
    test_messages = [f"Mensagem {i}" for i in range(10)]
    for msg in test_messages:
        sender.send(msg)
        time.sleep(0.1)
    
    recv_thread.join(timeout=5)
    
    # Verificar
    assert len(received_messages) == 10, f"Esperado 10 mensagens, recebido {len(received_messages)}"
    print(f"✓ Teste passou: {len(received_messages)} mensagens recebidas")
    print(f"  Retransmissões: {sender.get_retransmissions()}")
    
    sender.close()
    receiver.close()


def test_rdt20_corruption():
    """Teste rdt2.0 com corrupção."""
    print("\n=== Teste rdt2.0 - Corrupção ===")
    
    channel = UnreliableChannel(loss_rate=0.0, corrupt_rate=0.3, delay_range=(0.01, 0.1))
    sender = RDT20Sender(port=5020, dest_port=5021, channel=channel)
    receiver = RDT20Receiver(port=5021, channel=channel)
    
    received_messages = []
    def receive_loop():
        for _ in range(10):
            msg = receiver.receive(timeout=5)
            if msg:
                received_messages.append(msg)
    
    recv_thread = threading.Thread(target=receive_loop)
    recv_thread.start()
    
    test_messages = [f"Msg {i}" for i in range(10)]
    for msg in test_messages:
        sender.send(msg)
        time.sleep(0.2)
    
    recv_thread.join(timeout=30)
    
    assert len(received_messages) == 10
    print(f"✓ Teste passou: {len(received_messages)} mensagens recebidas")
    print(f"  Retransmissões: {sender.get_retransmissions()}")
    print(f"  Corrompidas: {receiver.get_stats()['corrupted']}")
    
    sender.close()
    receiver.close()


def test_rdt21_with_sequence():
    """Teste rdt2.1 com números de sequência."""
    print("\n=== Teste rdt2.1 - Números de Sequência ===")
    
    channel = UnreliableChannel(loss_rate=0.0, corrupt_rate=0.2, delay_range=(0.01, 0.1))
    sender = RDT21Sender(port=5030, dest_port=5031, channel=channel)
    receiver = RDT21Receiver(port=5031, channel=channel)
    
    received_messages = []
    def receive_loop():
        for _ in range(10):
            msg = receiver.receive(timeout=5)
            if msg:
                received_messages.append(msg)
    
    recv_thread = threading.Thread(target=receive_loop)
    recv_thread.start()
    
    test_messages = [f"Msg {i}" for i in range(10)]
    for msg in test_messages:
        sender.send(msg)
        time.sleep(0.2)
    
    recv_thread.join(timeout=30)
    
    assert len(received_messages) == 10
    stats = receiver.get_stats()
    print(f"✓ Teste passou: {len(received_messages)} mensagens recebidas")
    print(f"  Retransmissões: {sender.get_retransmissions()}")
    print(f"  Corrompidas: {stats['corrupted']}")
    print(f"  Duplicadas: {stats['duplicates']}")
    
    sender.close()
    receiver.close()


def test_rdt30_with_loss():
    """Teste rdt3.0 com perda de pacotes."""
    print("\n=== Teste rdt3.0 - Perda de Pacotes ===")
    
    channel = UnreliableChannel(loss_rate=0.15, corrupt_rate=0.1, delay_range=(0.05, 0.5))
    sender = RDT30Sender(port=5040, dest_port=5041, channel=channel)
    receiver = RDT30Receiver(port=5041, channel=channel)
    
    received_messages = []
    def receive_loop():
        for _ in range(10):
            msg = receiver.receive(timeout=10)
            if msg:
                received_messages.append(msg)
    
    recv_thread = threading.Thread(target=receive_loop)
    recv_thread.start()
    
    test_messages = [f"Msg {i}" for i in range(10)]
    for msg in test_messages:
        sender.send(msg)
        time.sleep(0.3)
    
    recv_thread.join(timeout=60)
    
    assert len(received_messages) == 10
    sender_stats = sender.get_stats()
    print(f"✓ Teste passou: {len(received_messages)} mensagens recebidas")
    print(f"  Retransmissões: {sender_stats['retransmissions']}")
    print(f"  Throughput: {sender_stats['throughput_mbps']:.4f} Mbps")
    
    sender.close()
    receiver.close()


if __name__ == '__main__':
    print("Executando testes da Fase 1...")
    
    try:
        test_rdt20_perfect_channel()
        test_rdt20_corruption()
        test_rdt21_with_sequence()
        test_rdt30_with_loss()
        
        print("\n✓ Todos os testes da Fase 1 passaram!")
    except AssertionError as e:
        print(f"\n✗ Teste falhou: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Erro: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

