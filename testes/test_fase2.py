"""
Testes automatizados para Fase 2 - Go-Back-N.
"""
import sys
import os
import time
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fase2.gbn import GBNSender, GBNReceiver
from utils.simulator import UnreliableChannel, DirectChannel


def test_gbn_efficiency():
    """Teste de eficiência do GBN comparado com stop-and-wait."""
    print("\n=== Teste GBN - Eficiência ===")
    
    channel = DirectChannel()
    
    # Teste com janela pequena (N=1, equivalente a stop-and-wait)
    sender1 = GBNSender(port=6010, dest_port=6011, channel=channel, window_size=1)
    receiver1 = GBNReceiver(port=6011, channel=channel)
    
    received1 = []
    def recv_loop1():
        for _ in range(20):
            msg = receiver1.receive(timeout=2)
            if msg:
                received1.append(msg)
    
    recv_thread1 = threading.Thread(target=recv_loop1)
    recv_thread1.start()
    
    start1 = time.time()
    for i in range(20):
        sender1.send(f"Msg {i}".encode())
        time.sleep(0.05)
    
    sender1.wait_for_all_acks()
    time1 = time.time() - start1
    recv_thread1.join(timeout=5)
    
    sender1.close()
    receiver1.close()
    
    # Teste com janela maior (N=5)
    sender2 = GBNSender(port=6020, dest_port=6021, channel=channel, window_size=5)
    receiver2 = GBNReceiver(port=6021, channel=channel)
    
    received2 = []
    def recv_loop2():
        for _ in range(20):
            msg = receiver2.receive(timeout=2)
            if msg:
                received2.append(msg)
    
    recv_thread2 = threading.Thread(target=recv_loop2)
    recv_thread2.start()
    
    start2 = time.time()
    for i in range(20):
        sender2.send(f"Msg {i}".encode())
        time.sleep(0.05)
    
    sender2.wait_for_all_acks()
    time2 = time.time() - start2
    recv_thread2.join(timeout=5)
    
    sender2.close()
    receiver2.close()
    
    print(f"✓ Teste passou:")
    print(f"  N=1 (stop-and-wait): {time1:.2f}s")
    print(f"  N=5 (GBN): {time2:.2f}s")
    print(f"  Melhoria: {(time1/time2):.2f}x")
    
    assert len(received1) == 20
    assert len(received2) == 20


def test_gbn_with_loss():
    """Teste GBN com perdas."""
    print("\n=== Teste GBN - Perdas ===")
    
    channel = UnreliableChannel(loss_rate=0.1, corrupt_rate=0.05, delay_range=(0.01, 0.2))
    sender = GBNSender(port=6030, dest_port=6031, channel=channel, window_size=5)
    receiver = GBNReceiver(port=6031, channel=channel)
    
    received = []
    def recv_loop():
        for _ in range(15):
            msg = receiver.receive(timeout=10)
            if msg:
                received.append(msg)
    
    recv_thread = threading.Thread(target=recv_loop)
    recv_thread.start()
    
    for i in range(15):
        sender.send(f"Msg {i}".encode())
        time.sleep(0.1)
    
    sender.wait_for_all_acks(timeout=60)
    recv_thread.join(timeout=10)
    
    print(f"✓ Teste passou: {len(received)} mensagens recebidas")
    print(f"  Retransmissões: {sender.get_retransmissions()}")
    stats = sender.get_stats()
    print(f"  Throughput: {stats['throughput_mbps']:.4f} Mbps")
    
    sender.close()
    receiver.close()
    
    assert len(received) == 15


def test_gbn_window_sizes():
    """Teste GBN com diferentes tamanhos de janela."""
    print("\n=== Teste GBN - Tamanhos de Janela ===")
    
    channel = DirectChannel()
    window_sizes = [1, 5, 10, 20]
    results = []
    
    for N in window_sizes:
        sender = GBNSender(port=6040+N, dest_port=6041+N, channel=channel, window_size=N)
        receiver = GBNReceiver(port=6041+N, channel=channel)
        
        received = []
        def recv_loop():
            for _ in range(30):
                msg = receiver.receive(timeout=2)
                if msg:
                    received.append(msg)
        
        recv_thread = threading.Thread(target=recv_loop)
        recv_thread.start()
        
        start = time.time()
        for i in range(30):
            sender.send(f"Msg {i}".encode())
            time.sleep(0.02)
        
        sender.wait_for_all_acks()
        elapsed = time.time() - start
        recv_thread.join(timeout=5)
        
        stats = sender.get_stats()
        throughput = stats['throughput_mbps']
        results.append((N, elapsed, throughput))
        
        sender.close()
        receiver.close()
        time.sleep(0.5)
    
    print(f"✓ Teste passou:")
    for N, elapsed, throughput in results:
        print(f"  N={N}: {elapsed:.2f}s, {throughput:.4f} Mbps")
    
    # Verificar que janelas maiores são mais rápidas
    assert results[0][1] > results[-1][1]  # N=1 deve ser mais lento que N=20


if __name__ == '__main__':
    print("Executando testes da Fase 2...")
    
    try:
        test_gbn_efficiency()
        test_gbn_with_loss()
        test_gbn_window_sizes()
        
        print("\n✓ Todos os testes da Fase 2 passaram!")
    except AssertionError as e:
        print(f"\n✗ Teste falhou: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Erro: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

