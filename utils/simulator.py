"""
Simulador de canal não confiável.
Simula perda de pacotes, corrupção e atraso.
"""
import random
import threading
import socket

from utils.packet import GBNPacket, Packet


class UnreliableChannel:
    """Simula um canal de rede não confiável."""
    
    def __init__(self, loss_rate=0.1, corrupt_rate=0.1, delay_range=(0.01, 0.5)):
        """
        Inicializa o simulador de canal.
        
        Args:
            loss_rate: probabilidade de perda de pacote (0.0 a 1.0)
            corrupt_rate: probabilidade de corrupção (0.0 a 1.0)
            delay_range: tupla (min_delay, max_delay) em segundos
        """
        self.loss_rate = loss_rate
        self.corrupt_rate = corrupt_rate
        self.delay_range = delay_range
    
    def send(self, packet, dest_socket, dest_addr):
        """
        Envia pacote através do canal não confiável.
        
        Args:
            packet: bytes do pacote a enviar
            dest_socket: socket de destino
            dest_addr: endereço de destino (host, port)
        """
        # Simular perda
        if random.random() < self.loss_rate:
            print(f"[SIMULADOR] Pacote perdido")
            return
        
        # Simular corrupção
        if random.random() < self.corrupt_rate:
            packet = self._corrupt_packet(packet)
            print(f"[SIMULADOR] Pacote corrompido")
        
        # Simular atraso
        delay = random.uniform(*self.delay_range)
        threading.Timer(delay, lambda: dest_socket.sendto(packet, dest_addr)).start()
    
    def _corrupt_packet(self, packet):
        """Corrompe bits aleatórios do pacote."""
        packet_list = list(packet)
        num_corruptions = random.randint(1, 5)
        for _ in range(num_corruptions):
            idx = random.randint(0, len(packet_list) - 1)
            packet_list[idx] = packet_list[idx] ^ 0xFF  # Inverter todos os bits
        return bytes(packet_list)
    
    def send_direct(self, packet, dest_socket, dest_addr):
        """Envia pacote diretamente sem simulação (para testes)."""
        dest_socket.sendto(packet, dest_addr)


class DirectChannel:
    """Canal direto sem simulação (para testes com canal perfeito)."""
    
    def send(self, packet, dest_socket, dest_addr):
        """Envia pacote diretamente."""
        dest_socket.sendto(packet, dest_addr)
    
    def send_direct(self, packet, dest_socket, dest_addr):
        """Alias para send."""
        dest_socket.sendto(packet, dest_addr)


class GBNBoundedLossChannel(UnreliableChannel):
    """
    Canal com perdas controladas para testes do GBN.

    - Apenas pacotes DATA podem ser descartados.
    - Cada sequência pode ser perdida no máximo uma vez (na primeira tentativa).
    - ACKs nunca são perdidos/corrompidos.
    """

    def __init__(self, loss_rate=0.1, corrupt_rate=0.0, delay_range=(0.01, 0.15)):
        super().__init__(loss_rate=loss_rate, corrupt_rate=corrupt_rate, delay_range=delay_range)
        # Estados possíveis por (tipo, seqnum):
        # "new" (ainda não enviado), "lost_once" (primeira tentativa perdida), "delivered" (já entregue)
        self._packet_state = {}

    def send(self, packet, dest_socket, dest_addr):
        packet_type = None
        seqnum = None
        key = None
        
        try:
            packet_type, seqnum, _, _ = GBNPacket.parse_packet(packet)
            key = (packet_type, seqnum)
        except Exception:
            # Se não for possível parsear (por exemplo, mensagem de controle),
            # tratamos como canal genérico.
            pass
        
        if key is not None and packet_type == Packet.TYPE_DATA:
            state = self._packet_state.get(key, "new")
            if state == "new":
                if random.random() < self.loss_rate:
                    self._packet_state[key] = "lost_once"
                    print(f"[SIMULADOR] Pacote DATA seq={seqnum} perdido (tentativa inicial)")
                    return
                self._packet_state[key] = "delivered"
            elif state == "lost_once":
                # Primeira retransmissão deve passar sem novas perdas.
                self._packet_state[key] = "delivered"
            # Se já foi entregue, mantemos o envio direto (sem drops adicionais).
        elif key is None and random.random() < self.loss_rate:
            # Pacotes sem formatação GBN (mensagens de controle) respeitam a taxa.
            print("[SIMULADOR] Pacote genérico perdido")
            return
        
        # ACKs nunca são perdidos e o canal de perdas não aplica corrupção adicional.
        delay = random.uniform(*self.delay_range)
        threading.Timer(delay, lambda: dest_socket.sendto(packet, dest_addr)).start()

