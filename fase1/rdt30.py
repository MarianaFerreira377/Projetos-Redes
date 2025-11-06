"""
Implementação do protocolo rdt3.0 - Canal com Erros de Bits, Números de Sequência e Timer.
Referência: Seção 3.4.1, Figura 3.15 - Kurose & Ross

FSM do Remetente (Figura 3.15):
- Estados: 4 estados (igual rdt2.1) mas com timer
  - "Esperar chamada 0 de cima" -> ações incluem start_timer()
  - "Esperar ACK 0" -> ações incluem stop_timer() ou start_timer() em timeout
  - "Esperar chamada 1 de cima" -> ações incluem start_timer()
  - "Esperar ACK 1" -> ações incluem stop_timer() ou start_timer() em timeout

FSM do Receptor (Figura 3.12):
- Mesmo do rdt2.1 (sem mudanças)
"""
import socket
import sys
import os
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.packet import RDT21Packet, Packet
from utils.logger import setup_logger


class RDT30Sender:
    """
    Remetente rdt3.0 - Implementação do FSM da Figura 3.15.
    Igual ao rdt2.1 mas com timer para detectar perda de pacotes.
    """
    
    # Estados do FSM (iguais ao rdt2.1)
    WAIT_CALL_0_FROM_ABOVE = "Esperar chamada 0 de cima"
    WAIT_ACK_0 = "Esperar ACK 0"
    WAIT_CALL_1_FROM_ABOVE = "Esperar chamada 1 de cima"
    WAIT_ACK_1 = "Esperar ACK 1"
    
    def __init__(self, host='localhost', port=5000, dest_host='localhost', dest_port=5001, channel=None, timeout=2.0):
        """
        Inicializa o remetente.
        
        Args:
            host: endereço local
            port: porta local
            dest_host: endereço de destino
            dest_port: porta de destino
            channel: canal não confiável
            timeout: timeout inicial em segundos
        """
        self.host = host
        self.port = port
        self.dest_addr = (dest_host, dest_port)
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((host, port))
        self.socket.settimeout(0.1)  # Timeout curto para verificar periodicamente
        self.channel = channel
        self.logger = setup_logger('RDT30Sender')
        self.retransmissions = 0
        self.timeout_interval = timeout
        self.timer = None
        self.timer_lock = threading.Lock()
        self.start_time = None
        self.bytes_sent = 0
        
        # Estado inicial do FSM
        self.state = self.WAIT_CALL_0_FROM_ABOVE
        self.sndpkt = None
    
    def start_timer(self):
        """
        Ação: start_timer() - inicia o temporizador de contagem regressiva.
        """
        with self.timer_lock:
            if self.timer:
                self.timer.cancel()
            self.timer = threading.Timer(self.timeout_interval, self._timeout_handler)
            self.timer.start()
            self.logger.debug("Timer iniciado")
    
    def stop_timer(self):
        """
        Ação: stop_timer() - para o temporizador.
        """
        with self.timer_lock:
            if self.timer:
                self.timer.cancel()
                self.timer = None
                self.logger.debug("Timer parado")
    
    def _timeout_handler(self):
        """
        Handler chamado quando o timer expira (evento: temporização).
        Ação: udt_send(sndpkt), start_timer()
        """
        self.logger.warning(f"[Estado: {self.state}] Timeout ocorreu (temporização), retransmitindo...")
        self.retransmissions += 1
        
        # Ação: udt_send(sndpkt)
        if self.sndpkt:
            self.udt_send(self.sndpkt)
        
        # Ação: start_timer()
        self.start_timer()
    
    def make_pkt(self, seqnum, data, checksum):
        """Ação: make_pkt(0, data, checksum) ou make_pkt(1, data, checksum)."""
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
    
    def isACK(self, rcvpkt, expected_seq):
        """
        Verifica se é ACK com número de sequência esperado.
        
        Args:
            rcvpkt: pacote recebido
            expected_seq: número de sequência esperado (0 ou 1)
        
        Returns:
            True se for ACK com seq esperado, False caso contrário
        """
        packet_type, ack_seq, _, is_valid = RDT21Packet.parse_packet(rcvpkt)
        return is_valid and packet_type == Packet.TYPE_ACK and ack_seq == expected_seq
    
    def rdt_send(self, data):
        """
        Método rdt_send - Evento de entrada na camada de transporte.
        
        Processa estados conforme Figura 3.15:
        - "Esperar chamada 0 de cima" -> enviar pacote seq=0, start_timer()
        - "Esperar chamada 1 de cima" -> enviar pacote seq=1, start_timer()
        """
        if isinstance(data, str):
            data = data.encode('utf-8')
        
        if self.start_time is None:
            self.start_time = time.time()
        self.bytes_sent += len(data)
        
        if self.state == self.WAIT_CALL_0_FROM_ABOVE:
            # Evento: rdt_send(data)
            # Ações: sndpkt = make_pkt(0, data, checksum), udt_send(sndpkt), start_timer()
            self.sndpkt = self.make_pkt(0, data, None)
            self.udt_send(self.sndpkt)
            self.start_timer()
            self.logger.info(f"[Estado: {self.state}] Pacote seq=0 enviado: {len(data)} bytes, timer iniciado")
            # Transição: -> "Esperar ACK 0"
            self.state = self.WAIT_ACK_0
            return self._wait_for_ack(0)
        
        elif self.state == self.WAIT_CALL_1_FROM_ABOVE:
            # Evento: rdt_send(data)
            # Ações: sndpkt = make_pkt(1, data, checksum), udt_send(sndpkt), start_timer()
            self.sndpkt = self.make_pkt(1, data, None)
            self.udt_send(self.sndpkt)
            self.start_timer()
            self.logger.info(f"[Estado: {self.state}] Pacote seq=1 enviado: {len(data)} bytes, timer iniciado")
            # Transição: -> "Esperar ACK 1"
            self.state = self.WAIT_ACK_1
            return self._wait_for_ack(1)
        
        else:
            self.logger.warning(f"rdt_send chamado em estado incorreto: {self.state}")
            return False
    
    def _wait_for_ack(self, expected_seq):
        """
        Implementa estados "Esperar ACK 0" ou "Esperar ACK 1".
        
        Processa eventos conforme Figura 3.15:
        - rdt_rcv(rcvpkt) && (corrupt(rcvpkt) || isACK(rcvpkt, 1-seq)) -> nenhuma ação (descarta)
        - rdt_rcv(rcvpkt) && notcorrupt(rcvpkt) && isACK(rcvpkt, seq) -> stop_timer()
        - temporização -> udt_send(sndpkt), start_timer()
        """
        while (self.state == self.WAIT_ACK_0) or (self.state == self.WAIT_ACK_1):
            try:
                # Evento: rdt_rcv(rcvpkt)
                rcvpkt, addr = self.socket.recvfrom(1024)
                packet_type, ack_seq, _, is_valid = RDT21Packet.parse_packet(rcvpkt)
                
                # Evento: rdt_rcv(rcvpkt) && (corrupt(rcvpkt) || isACK(rcvpkt, 1-seq))
                if self.corrupt(rcvpkt) or (is_valid and packet_type == Packet.TYPE_ACK and ack_seq != expected_seq):
                    # Ações: (nenhuma) - descarta o pacote
                    self.logger.debug(f"[Estado: {self.state}] ACK corrompido ou duplicado recebido, descartando")
                    # Permanece no estado (aguardando timeout ou ACK correto)
                    continue
                
                # Evento: rdt_rcv(rcvpkt) && notcorrupt(rcvpkt) && isACK(rcvpkt, seq)
                if self.isACK(rcvpkt, expected_seq):
                    self.logger.info(f"[Estado: {self.state}] ACK {expected_seq} correto recebido")
                    # Ação: stop_timer()
                    self.stop_timer()
                    
                    if expected_seq == 0:
                        # Transição: -> "Esperar chamada 1 de cima"
                        self.state = self.WAIT_CALL_1_FROM_ABOVE
                    else:
                        # Transição: -> "Esperar chamada 0 de cima"
                        self.state = self.WAIT_CALL_0_FROM_ABOVE
                    
                    self.sndpkt = None
                    return True
                
            except socket.timeout:
                # Timeout do socket - verificar se timer expirou
                # (o timer será tratado pelo _timeout_handler)
                continue
            except Exception as e:
                self.logger.error(f"Erro ao aguardar ACK: {e}")
                self.stop_timer()
                return False
        
        return False
    
    def send(self, data):
        """Alias para rdt_send para compatibilidade."""
        return self.rdt_send(data)
    
    def get_retransmissions(self):
        """Retorna número de retransmissões."""
        return self.retransmissions
    
    def get_stats(self):
        """Retorna estatísticas de envio."""
        end_time = time.time()
        total_time = end_time - self.start_time if self.start_time else 0
        throughput = (self.bytes_sent * 8) / total_time if total_time > 0 else 0
        
        return {
            'retransmissions': self.retransmissions,
            'bytes_sent': self.bytes_sent,
            'total_time': total_time,
            'throughput_bps': throughput,
            'throughput_mbps': throughput / 1_000_000
        }
    
    def get_state(self):
        """Retorna o estado atual do FSM."""
        return self.state
    
    def close(self):
        """Fecha o socket."""
        self.stop_timer()
        self.socket.close()


class RDT30Receiver:
    """
    Receptor rdt3.0 - Mesmo comportamento do rdt2.1 (sem mudanças).
    Implementação do FSM da Figura 3.12.
    """
    
    # Estados do FSM (iguais ao rdt2.1)
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
        self.logger = setup_logger('RDT30Receiver')
        self.expected_seq = 0
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
        """Ação: make_pkt(ACK, seq_num, checksum)."""
        return RDT21Packet.create_packet(ack_type, seq_num, b'')
    
    def udt_send(self, packet, addr):
        """Ação: udt_send(sndpkt)."""
        if self.channel:
            self.channel.send(packet, self.socket, addr)
        else:
            self.socket.sendto(packet, addr)
    
    def extract(self, rcvpkt, data):
        """Ação: extract(rcvpkt, data)."""
        _, _, extracted_data, _ = RDT21Packet.parse_packet(rcvpkt)
        return extracted_data
    
    def deliver_data(self, data):
        """Ação: deliver_data(data)."""
        self.received_count += 1
        self.messages.append(data)
        self.logger.info(f"Dados entregues para camada superior: {len(data)} bytes")
    
    def rdt_rcv(self, timeout=None):
        """
        Método rdt_rcv - Evento de entrada na camada de transporte.
        
        Implementa FSM conforme Figura 3.12 (igual ao rdt2.1).
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
                    self.logger.warning(f"[Estado: {self.state}] Pacote corrompido recebido, reenviando ACK")
                    self.corrupted_count += 1
                    # Reenviar ACK do último pacote entregue (ainda não recebeu seq=0, então não há ACK anterior)
                    sndpkt = self.make_pkt(Packet.TYPE_ACK, 1, None)  # ACK com seq incorreto
                    self.udt_send(sndpkt, addr)
                    return None
                
                # Evento: rdt_rcv(rcvpkt) && notcorrupt(rcvpkt) && has_seq1(rcvpkt)
                if self.notcorrupt(rcvpkt) and self.has_seq1(rcvpkt):
                    self.logger.warning(f"[Estado: {self.state}] Pacote seq=1 recebido (esperado seq=0), reenviando ACK")
                    # Reenviar ACK
                    sndpkt = self.make_pkt(Packet.TYPE_ACK, 1, None)
                    self.udt_send(sndpkt, addr)
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
                    self.logger.warning(f"[Estado: {self.state}] Pacote corrompido recebido, reenviando ACK")
                    self.corrupted_count += 1
                    # Reenviar ACK do último pacote entregue (seq=0)
                    sndpkt = self.make_pkt(Packet.TYPE_ACK, 0, None)
                    self.udt_send(sndpkt, addr)
                    return None
                
                # Evento: rdt_rcv(rcvpkt) && notcorrupt(rcvpkt) && has_seq0(rcvpkt)
                if self.notcorrupt(rcvpkt) and self.has_seq0(rcvpkt):
                    self.logger.warning(f"[Estado: {self.state}] Pacote seq=0 recebido (esperado seq=1), reenviando ACK")
                    self.duplicate_count += 1
                    # Reenviar ACK do último pacote entregue (seq=0)
                    sndpkt = self.make_pkt(Packet.TYPE_ACK, 0, None)
                    self.udt_send(sndpkt, addr)
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
