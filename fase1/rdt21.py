"""
Implementação do protocolo rdt2.1 - Canal com Erros de Bits e Números de Sequência.
Referência: Seção 3.4.1, Figuras 3.11 e 3.12 - Kurose & Ross

FSM do Remetente (Figura 3.11):
- Estado 1: "Esperar chamada 0 de cima"
- Estado 2: "Esperar ACK ou NAK 0"
- Estado 3: "Esperar chamada 1 de cima"
- Estado 4: "Esperar ACK ou NAK 1"

FSM do Receptor (Figura 3.12):
- Estado 1: "Esperar 0 de baixo"
- Estado 2: "Esperar 1 de baixo"
"""
import socket
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.packet import RDT21Packet, Packet
from utils.logger import setup_logger


class RDT21Sender:
    """
    Remetente rdt2.1 - Implementação do FSM da Figura 3.11.
    """
    
    # Estados do FSM
    WAIT_CALL_0_FROM_ABOVE = "Esperar chamada 0 de cima"
    WAIT_ACK_OR_NAK_0 = "Esperar ACK ou NAK 0"
    WAIT_CALL_1_FROM_ABOVE = "Esperar chamada 1 de cima"
    WAIT_ACK_OR_NAK_1 = "Esperar ACK ou NAK 1"
    
    def __init__(self, host='localhost', port=5000, dest_host='localhost', dest_port=5001, channel=None):
        """
        Inicializa o remetente.
        
        Args:
            host: endereço local
            port: porta local
            dest_host: endereço de destino
            dest_port: porta de destino
            channel: canal não confiável
        """
        self.host = host
        self.port = port
        self.dest_addr = (dest_host, dest_port)
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((host, port))
        self.socket.settimeout(5.0)
        self.channel = channel
        self.logger = setup_logger('RDT21Sender')
        self.retransmissions = 0
        
        # Estado inicial do FSM
        self.state = self.WAIT_CALL_0_FROM_ABOVE
        self.sndpkt = None  # Pacote armazenado para retransmissão
    
    def make_pkt(self, seqnum, data, checksum):
        """
        Ação: make_pkt(0, data, checksum) ou make_pkt(1, data, checksum).
        
        Args:
            seqnum: número de sequência (0 ou 1)
            data: dados
            checksum: checksum (calculado internamente)
        
        Returns:
            pacote criado
        """
        return RDT21Packet.create_packet(Packet.TYPE_DATA, seqnum, data)
    
    def udt_send(self, packet):
        """Ação: udt_send(sndpkt)."""
        if self.channel:
            self.channel.send(packet, self.socket, self.dest_addr)
        else:
            self.socket.sendto(packet, self.dest_addr)
    
    def corrupt(self, rcvpkt):
        """Verifica se o pacote está corrompido."""
        _, _, _, is_valid = RDT21Packet.parse_packet(rcvpkt)
        return not is_valid
    
    def isNAK(self, rcvpkt):
        """Verifica se é NAK."""
        packet_type, _, _, is_valid = RDT21Packet.parse_packet(rcvpkt)
        return is_valid and packet_type == Packet.TYPE_NAK
    
    def isACK(self, rcvpkt):
        """Verifica se é ACK."""
        packet_type, _, _, is_valid = RDT21Packet.parse_packet(rcvpkt)
        return is_valid and packet_type == Packet.TYPE_ACK
    
    def rdt_send(self, data):
        """
        Método rdt_send - Evento de entrada na camada de transporte.
        
        Processa estados:
        - "Esperar chamada 0 de cima" -> enviar pacote seq=0
        - "Esperar chamada 1 de cima" -> enviar pacote seq=1
        """
        if isinstance(data, str):
            data = data.encode('utf-8')
        
        if self.state == self.WAIT_CALL_0_FROM_ABOVE:
            # Evento: rdt_send(data)
            # Ações: sndpkt = make_pkt(0, data, checksum), udt_send(sndpkt)
            self.sndpkt = self.make_pkt(0, data, None)
            self.udt_send(self.sndpkt)
            self.logger.info(f"[Estado: {self.state}] Pacote seq=0 enviado: {len(data)} bytes")
            # Transição: -> "Esperar ACK ou NAK 0"
            self.state = self.WAIT_ACK_OR_NAK_0
            return self._wait_for_ack_or_nak(0)
        
        elif self.state == self.WAIT_CALL_1_FROM_ABOVE:
            # Evento: rdt_send(data)
            # Ações: sndpkt = make_pkt(1, data, checksum), udt_send(sndpkt)
            self.sndpkt = self.make_pkt(1, data, None)
            self.udt_send(self.sndpkt)
            self.logger.info(f"[Estado: {self.state}] Pacote seq=1 enviado: {len(data)} bytes")
            # Transição: -> "Esperar ACK ou NAK 1"
            self.state = self.WAIT_ACK_OR_NAK_1
            return self._wait_for_ack_or_nak(1)
        
        else:
            self.logger.warning(f"rdt_send chamado em estado incorreto: {self.state}")
            return False
    
    def _wait_for_ack_or_nak(self, expected_seq):
        """
        Implementa estados "Esperar ACK ou NAK 0" ou "Esperar ACK ou NAK 1".
        
        Processa eventos conforme Figura 3.11.
        """
        while (self.state == self.WAIT_ACK_OR_NAK_0) or (self.state == self.WAIT_ACK_OR_NAK_1):
            try:
                # Evento: rdt_rcv(rcvpkt)
                rcvpkt, addr = self.socket.recvfrom(1024)
                packet_type, ack_seq, _, is_valid = RDT21Packet.parse_packet(rcvpkt)
                
                # Evento: rdt_rcv(rcvpkt) && (corrupt(rcvpkt) || isNAK(rcvpkt))
                if self.corrupt(rcvpkt) or self.isNAK(rcvpkt):
                    self.logger.warning(f"[Estado: {self.state}] ACK/NAK corrompido ou NAK recebido, retransmitindo...")
                    self.retransmissions += 1
                    # Ação: udt_send(sndpkt)
                    self.udt_send(self.sndpkt)
                    # Transição: permanece no mesmo estado
                    continue
                
                # Evento: rdt_rcv(rcvpkt) && notcorrupt(rcvpkt) && isACK(rcvpkt)
                if self.isACK(rcvpkt) and is_valid:
                    if expected_seq == 0 and self.state == self.WAIT_ACK_OR_NAK_0:
                        # ACK 0 recebido corretamente
                        self.logger.info(f"[Estado: {self.state}] ACK 0 recebido, alternando para seq=1")
                        # Transição: -> "Esperar chamada 1 de cima"
                        self.state = self.WAIT_CALL_1_FROM_ABOVE
                        self.sndpkt = None
                        return True
                    elif expected_seq == 1 and self.state == self.WAIT_ACK_OR_NAK_1:
                        # ACK 1 recebido corretamente
                        self.logger.info(f"[Estado: {self.state}] ACK 1 recebido, alternando para seq=0")
                        # Transição: -> "Esperar chamada 0 de cima"
                        self.state = self.WAIT_CALL_0_FROM_ABOVE
                        self.sndpkt = None
                        return True
                    else:
                        # ACK com número de sequência incorreto (duplicado)
                        self.logger.warning(f"[Estado: {self.state}] ACK duplicado recebido, retransmitindo...")
                        self.retransmissions += 1
                        self.udt_send(self.sndpkt)
                        continue
                        
            except socket.timeout:
                self.logger.warning(f"[Estado: {self.state}] Timeout aguardando ACK/NAK, retransmitindo...")
                self.retransmissions += 1
                self.udt_send(self.sndpkt)
                continue
            except Exception as e:
                self.logger.error(f"Erro ao aguardar ACK/NAK: {e}")
                return False
        
        return False
    
    def send(self, data):
        """Alias para rdt_send para compatibilidade."""
        return self.rdt_send(data)
    
    def get_retransmissions(self):
        """Retorna número de retransmissões."""
        return self.retransmissions
    
    def get_state(self):
        """Retorna o estado atual do FSM."""
        return self.state
    
    def close(self):
        """Fecha o socket."""
        self.socket.close()


class RDT21Receiver:
    """
    Receptor rdt2.1 - Implementação do FSM da Figura 3.12.
    """
    
    # Estados do FSM
    WAIT_0_FROM_BELOW = "Esperar 0 de baixo"
    WAIT_1_FROM_BELOW = "Esperar 1 de baixo"
    
    def __init__(self, host='localhost', port=5001, channel=None):
        """
        Inicializa o receptor.
        
        Args:
            host: endereço local
            port: porta local
            channel: canal não confiável
        """
        self.host = host
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((host, port))
        self.channel = channel
        self.logger = setup_logger('RDT21Receiver')
        self.messages = []
        self.received_count = 0
        self.corrupted_count = 0
        self.duplicate_count = 0
        
        # Estado inicial do FSM
        self.state = self.WAIT_0_FROM_BELOW
    
    def has_seq0(self, rcvpkt):
        """Verifica se o pacote tem número de sequência 0."""
        _, seq_num, _, is_valid = RDT21Packet.parse_packet(rcvpkt)
        return is_valid and seq_num == 0
    
    def has_seq1(self, rcvpkt):
        """Verifica se o pacote tem número de sequência 1."""
        _, seq_num, _, is_valid = RDT21Packet.parse_packet(rcvpkt)
        return is_valid and seq_num == 1
    
    def corrupt(self, rcvpkt):
        """Verifica se o pacote está corrompido."""
        _, _, _, is_valid = RDT21Packet.parse_packet(rcvpkt)
        return not is_valid
    
    def notcorrupt(self, rcvpkt):
        """Verifica se o pacote não está corrompido."""
        return not self.corrupt(rcvpkt)
    
    def make_pkt(self, ack_type, seq_num, checksum):
        """
        Ação: make_pkt(ACK, 0, checksum) ou make_pkt(NAK, checksum).
        
        Args:
            ack_type: tipo (ACK ou NAK)
            seq_num: número de sequência do pacote confirmado (para ACK)
            checksum: checksum (calculado internamente)
        
        Returns:
            pacote criado
        """
        # Para NAK, usar seq_num=0 (não usado)
        # Para ACK, incluir o número de sequência do pacote confirmado
        return RDT21Packet.create_packet(ack_type, seq_num, b'')
    
    def udt_send(self, packet, addr):
        """Ação: udt_send(sndpkt)."""
        if self.channel:
            self.channel.send(packet, self.socket, addr)
        else:
            self.socket.sendto(packet, addr)
    
    def extract(self, rcvpkt, data):
        """Ação: extract(rcvpkt, data) - extrai dados do pacote."""
        _, _, extracted_data, _ = RDT21Packet.parse_packet(rcvpkt)
        return extracted_data
    
    def deliver_data(self, data):
        """Ação: deliver_data(data) - entrega dados para camada superior."""
        self.received_count += 1
        self.messages.append(data)
        self.logger.info(f"Dados entregues para camada superior: {len(data)} bytes")
    
    def rdt_rcv(self, timeout=None):
        """
        Método rdt_rcv - Evento de entrada na camada de transporte.
        
        Implementa FSM conforme Figura 3.12.
        """
        if timeout:
            self.socket.settimeout(timeout)
        
        try:
            # Evento: rdt_rcv(rcvpkt)
            rcvpkt, addr = self.socket.recvfrom(1024)
            packet_type, seq_num, _, is_valid = RDT21Packet.parse_packet(rcvpkt)
            
            if packet_type != Packet.TYPE_DATA:
                return None
            
            # Estado: "Esperar 0 de baixo"
            if self.state == self.WAIT_0_FROM_BELOW:
                # Evento: rdt_rcv(rcvpkt) && corrupt(rcvpkt)
                if self.corrupt(rcvpkt):
                    self.logger.warning(f"[Estado: {self.state}] Pacote corrompido recebido, enviando NAK")
                    self.corrupted_count += 1
                    # Ações: sndpkt = make_pkt(NAK, checksum), udt_send(sndpkt)
                    sndpkt = self.make_pkt(Packet.TYPE_NAK, 0, None)
                    self.udt_send(sndpkt, addr)
                    # Permanece no estado
                    return None
                
                # Evento: rdt_rcv(rcvpkt) && notcorrupt(rcvpkt) && has_seq1(rcvpkt)
                if self.notcorrupt(rcvpkt) and self.has_seq1(rcvpkt):
                    self.logger.warning(f"[Estado: {self.state}] Pacote seq=1 recebido (esperado seq=0), reenviando ACK")
                    # Reenviar ACK do último pacote entregue (seq=0 não foi entregue ainda, então ACK com seq anterior)
                    # Como ainda não recebeu seq=0, não há ACK anterior para reenviar
                    # Enviar NAK implícito ou ACK com seq incorreto
                    sndpkt = self.make_pkt(Packet.TYPE_ACK, 1, None)  # ACK com seq incorreto indica problema
                    self.udt_send(sndpkt, addr)
                    # Permanece no estado
                    return None
                
                # Evento: rdt_rcv(rcvpkt) && notcorrupt(rcvpkt) && has_seq0(rcvpkt)
                if self.notcorrupt(rcvpkt) and self.has_seq0(rcvpkt):
                    self.logger.info(f"[Estado: {self.state}] Pacote seq=0 correto recebido")
                    # Ações: extract(rcvpkt, data), deliver_data(data)
                    data = self.extract(rcvpkt, None)
                    self.deliver_data(data)
                    # Ações: sndpkt = make_pkt(ACK, 0, checksum), udt_send(sndpkt)
                    sndpkt = self.make_pkt(Packet.TYPE_ACK, 0, None)
                    self.udt_send(sndpkt, addr)
                    # Transição: -> "Esperar 1 de baixo"
                    self.state = self.WAIT_1_FROM_BELOW
                    return data
            
            # Estado: "Esperar 1 de baixo"
            elif self.state == self.WAIT_1_FROM_BELOW:
                # Evento: rdt_rcv(rcvpkt) && corrupt(rcvpkt)
                if self.corrupt(rcvpkt):
                    self.logger.warning(f"[Estado: {self.state}] Pacote corrompido recebido, enviando NAK")
                    self.corrupted_count += 1
                    # Ações: sndpkt = make_pkt(NAK, checksum), udt_send(sndpkt)
                    sndpkt = self.make_pkt(Packet.TYPE_NAK, 0, None)
                    self.udt_send(sndpkt, addr)
                    # Permanece no estado
                    return None
                
                # Evento: rdt_rcv(rcvpkt) && notcorrupt(rcvpkt) && has_seq0(rcvpkt)
                if self.notcorrupt(rcvpkt) and self.has_seq0(rcvpkt):
                    self.logger.warning(f"[Estado: {self.state}] Pacote seq=0 recebido (esperado seq=1), reenviando ACK")
                    self.duplicate_count += 1
                    # Reenviar ACK do último pacote entregue (seq=0)
                    sndpkt = self.make_pkt(Packet.TYPE_ACK, 0, None)
                    self.udt_send(sndpkt, addr)
                    # Permanece no estado
                    return None
                
                # Evento: rdt_rcv(rcvpkt) && notcorrupt(rcvpkt) && has_seq1(rcvpkt)
                if self.notcorrupt(rcvpkt) and self.has_seq1(rcvpkt):
                    self.logger.info(f"[Estado: {self.state}] Pacote seq=1 correto recebido")
                    # Ações: extract(rcvpkt, data), deliver_data(data)
                    data = self.extract(rcvpkt, None)
                    self.deliver_data(data)
                    # Ações: sndpkt = make_pkt(ACK, 1, checksum), udt_send(sndpkt)
                    sndpkt = self.make_pkt(Packet.TYPE_ACK, 1, None)
                    self.udt_send(sndpkt, addr)
                    # Transição: -> "Esperar 0 de baixo"
                    self.state = self.WAIT_0_FROM_BELOW
                    return data
            
            return None
                
        except socket.timeout:
            self.logger.info(f"[Estado: {self.state}] Timeout na recepção")
            return None
        except Exception as e:
            self.logger.error(f"Erro ao receber: {e}")
            return None
    
    def receive(self, timeout=None):
        """Alias para rdt_rcv para compatibilidade."""
        return self.rdt_rcv(timeout)
    
    def get_all_messages(self):
        """Retorna todas as mensagens recebidas."""
        return self.messages
    
    def get_stats(self):
        """Retorna estatísticas de recepção."""
        return {
            'received': self.received_count,
            'corrupted': self.corrupted_count,
            'duplicates': self.duplicate_count
        }
    
    def get_state(self):
        """Retorna o estado atual do FSM."""
        return self.state
    
    def close(self):
        """Fecha o socket."""
        self.socket.close()
