"""
Servidor de exemplo usando TCP simplificado.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fase3.tcp_socket import SimpleTCPSocket


def main():
    """Função principal do servidor."""
    print("=== Servidor TCP Simplificado ===")
    
    server = SimpleTCPSocket(8000)
    server.listen()
    
    print("Aguardando conexão...")
    conn = server.accept()
    
    print("Conexão estabelecida!")
    
    # Receber dados
    data = conn.recv(10240)
    print(f"Dados recebidos: {len(data)} bytes")
    print(f"Primeiros 100 bytes: {data[:100]}")
    
    # Encerrar conexão
    conn.close()
    print("Conexão encerrada")


if __name__ == '__main__':
    main()

