"""
Cliente de exemplo usando TCP simplificado.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fase3.tcp_socket import SimpleTCPSocket


def main():
    """Função principal do cliente."""
    print("=== Cliente TCP Simplificado ===")
    
    client = SimpleTCPSocket(9000)
    
    print("Conectando ao servidor...")
    client.connect(('localhost', 8000))
    
    print("Conexão estabelecida!")
    
    # Enviar dados
    data = b'x' * 10240  # 10KB de dados
    print(f"Enviando {len(data)} bytes...")
    client.send(data)
    
    # Estatísticas
    stats = client.get_stats()
    print(f"\nEstatísticas:")
    print(f"  Bytes enviados: {stats['bytes_sent']}")
    print(f"  Retransmissões: {stats['retransmissions']}")
    print(f"  Throughput: {stats['throughput_sent_mbps']:.2f} Mbps")
    
    # Encerrar conexão
    client.close()
    print("Conexão encerrada")


if __name__ == '__main__':
    main()

