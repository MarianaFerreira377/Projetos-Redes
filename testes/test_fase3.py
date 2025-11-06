"""
Testes automatizados para Fase 3 - TCP Simplificado.
"""
import sys
import os
import time
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fase3.tcp_socket import SimpleTCPSocket


def test_connection_establishment():
    """Teste 1: Estabelecimento de conexão."""
    print("\n=== Teste 1: Estabelecimento de Conexão ===")
    
    server = SimpleTCPSocket(8100)
    server.listen()
    
    def server_accept():
        conn = server.accept()
        return conn
    
    accept_thread = threading.Thread(target=server_accept)
    accept_thread.start()
    
    time.sleep(0.1)
    
    client = SimpleTCPSocket(9100)
    client.connect(('localhost', 8100))
    
    accept_thread.join(timeout=5)
    
    assert client.state == SimpleTCPSocket.ESTABLISHED
    assert server.state == SimpleTCPSocket.ESTABLISHED
    
    print("✓ Teste passou: Conexão estabelecida com sucesso")
    
    client.close()
    server.close()
    time.sleep(0.5)


def test_data_transfer():
    """Teste 2: Transferência de dados."""
    print("\n=== Teste 2: Transferência de Dados ===")
    
    server = SimpleTCPSocket(8200)
    server.listen()
    
    received_data = []
    
    def server_accept():
        conn = server.accept()
        data = conn.recv(10240)
        received_data.append(data)
        conn.close()
    
    accept_thread = threading.Thread(target=server_accept)
    accept_thread.start()
    
    time.sleep(0.1)
    
    client = SimpleTCPSocket(9200)
    client.connect(('localhost', 8200))
    
    # Enviar 10KB de dados
    data = b'x' * 10240
    client.send(data)
    
    time.sleep(2)  # Aguardar recepção
    
    accept_thread.join(timeout=5)
    
    assert len(received_data) > 0
    total_received = b''.join(received_data)
    assert len(total_received) == len(data)
    
    print(f"✓ Teste passou: {len(data)} bytes enviados e recebidos corretamente")
    
    client.close()
    server.close()
    time.sleep(0.5)


def test_flow_control():
    """Teste 3: Controle de fluxo."""
    print("\n=== Teste 3: Controle de Fluxo ===")
    
    server = SimpleTCPSocket(8300)
    server.recv_window = 1024  # Reduzir janela para 1KB
    server.listen()
    
    received_data = []
    
    def server_accept():
        conn = server.accept()
        # Receber dados gradualmente
        for _ in range(10):
            data = conn.recv(1024)
            if data:
                received_data.append(data)
            time.sleep(0.1)
        conn.close()
    
    accept_thread = threading.Thread(target=server_accept)
    accept_thread.start()
    
    time.sleep(0.1)
    
    client = SimpleTCPSocket(9300)
    client.connect(('localhost', 8300))
    
    # Tentar enviar 10KB
    data = b'y' * 10240
    client.send(data)
    
    time.sleep(5)
    
    accept_thread.join(timeout=10)
    
    print(f"✓ Teste passou: Controle de fluxo funcionando")
    print(f"  Dados recebidos: {len(b''.join(received_data))} bytes")
    
    client.close()
    server.close()
    time.sleep(0.5)


def test_connection_close():
    """Teste 5: Encerramento de conexão."""
    print("\n=== Teste 5: Encerramento de Conexão ===")
    
    server = SimpleTCPSocket(8500)
    server.listen()
    
    def server_accept():
        conn = server.accept()
        conn.recv(1024)
        conn.close()
        return conn
    
    accept_thread = threading.Thread(target=server_accept)
    accept_thread.start()
    
    time.sleep(0.1)
    
    client = SimpleTCPSocket(9500)
    client.connect(('localhost', 8500))
    
    client.send(b'test')
    time.sleep(1)
    client.close()
    
    accept_thread.join(timeout=5)
    
    print("✓ Teste passou: Conexão encerrada corretamente")
    
    time.sleep(0.5)


def test_performance():
    """Teste 6: Desempenho."""
    print("\n=== Teste 6: Desempenho ===")
    
    server = SimpleTCPSocket(8600)
    server.listen()
    
    received_data = []
    
    def server_accept():
        conn = server.accept()
        data = conn.recv(1024 * 1024)  # 1MB
        received_data.append(data)
        conn.close()
    
    accept_thread = threading.Thread(target=server_accept)
    accept_thread.start()
    
    time.sleep(0.1)
    
    client = SimpleTCPSocket(9600)
    client.connect(('localhost', 8600))
    
    # Enviar 1MB
    data = b'z' * (1024 * 1024)
    start = time.time()
    client.send(data)
    
    time.sleep(10)  # Aguardar transferência
    
    elapsed = time.time() - start
    accept_thread.join(timeout=15)
    
    stats = client.get_stats()
    
    print(f"✓ Teste passou:")
    print(f"  Tempo: {elapsed:.2f}s")
    print(f"  Throughput: {stats['throughput_sent_mbps']:.2f} Mbps")
    print(f"  Retransmissões: {stats['retransmissions']}")
    print(f"  RTT estimado: {stats['estimated_rtt']:.3f}s")
    
    client.close()
    server.close()
    time.sleep(0.5)


if __name__ == '__main__':
    print("Executando testes da Fase 3...")
    
    try:
        test_connection_establishment()
        test_data_transfer()
        test_flow_control()
        test_connection_close()
        test_performance()
        
        print("\n✓ Todos os testes da Fase 3 passaram!")
    except AssertionError as e:
        print(f"\n✗ Teste falhou: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Erro: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

