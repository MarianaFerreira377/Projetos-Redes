"""
Implementação do protocolo rdt2.0 - Canal com Erros de Bits.
Referência: Seção 3.4.1, Figura 3.10 - Kurose & Ross

FSM do Remetente (Figura 3.10a):
- Estado 1: "Esperar chamada de cima"
  - Evento: rdt_send(data)
  - Ações: sndpkt = make_pkt(data, checksum), udt_send(sndpkt)
  - Transição: -> Estado 2

- Estado 2: "Esperar ACK ou NAK"
  - Evento: rdt_rcv(rcvpkt) && isNAK(rcvpkt)
  - Ações: udt_send(sndpkt)
  - Transição: -> Estado 2 (permanece)
  
  - Evento: rdt_rcv(rcvpkt) && corrupt(rcvpkt)
  - Ações: udt_send(sndpkt)
  - Transição: -> Estado 2 (permanece)
  
  - Evento: rdt_rcv(rcvpkt) && isACK(rcvpkt)
  - Ações: (nenhuma)
  - Transição: -> Estado 1

FSM do Receptor (Figura 3.10b):
- Estado: "Esperar chamada de baixo"
  - Evento: rdt_rcv(rcvpkt) && corrupt(rcvpkt)
  - Ações: sndpkt = make_pkt(NAK), udt_send(sndpkt)
  - Transição: -> Estado (permanece)
  
  - Evento: rdt_rcv(rcvpkt) && notcorrupt(rcvpkt)
  - Ações: extract(rcvpkt, data), deliver_data(data), sndpkt = make_pkt(ACK), udt_send(sndpkt)
  - Transição: -> Estado (permanece)
"""
import socket
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.packet import RDT20Packet, Packet
from utils.logger import setup_logger


class RDT20Sender:
    """
    Remetente rdt2.0 - Implementação do FSM da Figura 3.10a.
    """
    
    # Estados do FSM
    WAIT_CALL_FROM_ABOVE = "Esperar chamada de cima"
    WAIT_ACK_OR_NAK = "Esperar ACK ou NAK"
    
    def __init__(self, host='localhost', port=5000, dest_host='localhost', dest_port=5001, channel=None):
        """
        Inicializa o remetente.
        
        Args:
            host: endereço local
            port: porta local
            dest_host: endereço de destino
            dest_port: porta de destino
            channel: canal não confiável (usado no simulador)
        """
        self.host = host
        self.port = port
        self.dest_addr = (dest_host, dest_port)
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((host, port))
        self.socket.settimeout(5.0)
        self.channel = channel
        self.logger = setup_logger('RDT20Sender')
        self.retransmissions = 0
        
        # Estado inicial do FSM
        self.state = self.WAIT_CALL_FROM_ABOVE
        self.sndpkt = None  # Pacote armazenado para retransmissão
    
    def make_pkt(self, data, checksum):
        """
        Ação: make_pkt(data, checksum) - cria pacote com dados e checksum.
        
        Args:
            data: dados a empacotar
            checksum: checksum (calculado internamente)
        
        Returns:
            pacote criado
        """
        return RDT20Packet.create_packet(Packet.TYPE_DATA, data)
    
    def udt_send(self, packet):
        """
        Ação: udt_send(packet) - envia pacote via canal não confiável subjacente.
        
        Args:
            packet: pacote a enviar
        """
        if self.channel:
            self.channel.send(packet, self.socket, self.dest_addr)
        else:
            self.socket.sendto(packet, self.dest_addr)
    
    def isNAK(self, packet):
        """
        Verifica se o pacote recebido é um NAK.
        
        Args:
            packet: pacote recebido
        
        Returns:
            True se for NAK, False caso contrário
        """
        packet_type, _, _ = RDT20Packet.parse_packet(packet)
        return packet_type == Packet.TYPE_NAK
    
    def isACK(self, packet):
        """
        Verifica se o pacote recebido é um ACK.
        
        Args:
            packet: pacote recebido
        
        Returns:
            True se for ACK, False caso contrário
        """
        packet_type, _, _ = RDT20Packet.parse_packet(packet)
        return packet_type == Packet.TYPE_ACK
    
    def corrupt(self, packet):
        """
        Verifica se o pacote está corrompido.
        
        Args:
            packet: pacote recebido
        
        Returns:
            True se corrompido, False caso contrário
        """
        _, _, is_valid = RDT20Packet.parse_packet(packet)
        return not is_valid
    
    @staticmethod
    def _format_data(data: bytes, limit: int = 30) -> str:
        """Formata os dados para exibição em logs."""
        preview = data[:limit]
        try:
            text = preview.decode('utf-8', errors='replace')
        except Exception:
            text = repr(preview)
        suffix = '...' if len(data) > limit else ''
        return f"'{text}'{suffix}"
    
    def _format_packet_payload(self, packet: bytes) -> str:
        """Extrai e formata o payload de um pacote DATA."""
        if not packet:
            return "<vazio>"
        pkt_type, payload, _ = RDT20Packet.parse_packet(packet)
        if pkt_type != Packet.TYPE_DATA:
            return "<controle>"
        return self._format_data(payload)
    
    def rdt_send(self, data):
        """
        Método rdt_send - Evento de entrada na camada de transporte.
        
        Implementa Estado 1: "Esperar chamada de cima"
        - Evento: rdt_send(data)
        - Ações: sndpkt = make_pkt(data, checksum), udt_send(sndpkt)
        - Transição: -> Estado 2
        
        Args:
            data: bytes a enviar
        
        Returns:
            True se enviado com sucesso, False caso contrário
        """
        if self.state != self.WAIT_CALL_FROM_ABOVE:
            self.logger.warning(f"rdt_send chamado em estado incorreto: {self.state}")
            return False
        
        if isinstance(data, str):
            data = data.encode('utf-8')
        
        # Ação: sndpkt = make_pkt(data, checksum)
        self.sndpkt = self.make_pkt(data, None)
        
        # Ação: udt_send(sndpkt)
        self.udt_send(self.sndpkt)
        
        self.logger.info(
            f"\n[Estado: {self.state}] Pacote enviado: {len(data)} bytes | Dados: {self._format_data(data)}"
        )
        
        # Transição: Estado 1 -> Estado 2
        self.state = self.WAIT_ACK_OR_NAK
        self.logger.debug(f"Transição: {self.WAIT_CALL_FROM_ABOVE} -> {self.WAIT_ACK_OR_NAK}")
        
        # Aguardar ACK ou NAK (Estado 2)
        return self._wait_for_ack_or_nak()
    
    def _wait_for_ack_or_nak(self):
        """
        Implementa Estado 2: "Esperar ACK ou NAK".
        
        Processa eventos:
        - rdt_rcv(rcvpkt) && isNAK(rcvpkt) -> udt_send(sndpkt)
        - rdt_rcv(rcvpkt) && corrupt(rcvpkt) -> udt_send(sndpkt)
        - rdt_rcv(rcvpkt) && isACK(rcvpkt) -> voltar ao Estado 1
        """
        while self.state == self.WAIT_ACK_OR_NAK:
            try:
                # Evento: rdt_rcv(rcvpkt) - receber pacote do canal
                rcvpkt, addr = self.socket.recvfrom(1024)
                
                # Evento: rdt_rcv(rcvpkt) && isNAK(rcvpkt)
                if self.isNAK(rcvpkt):
                    self.logger.warning(
                        f"\n[Estado: {self.state}] NAK recebido, retransmitindo dados: {self._format_packet_payload(self.sndpkt)}"
                    )
                    self.retransmissions += 1
                    # Ação: udt_send(sndpkt)
                    self.udt_send(self.sndpkt)
                    # Transição: Estado 2 -> Estado 2 (permanece)
                    continue
                
                # Evento: rdt_rcv(rcvpkt) && corrupt(rcvpkt)
                if self.corrupt(rcvpkt):
                    self.logger.warning(
                        f"\n[Estado: {self.state}] ACK/NAK corrompido recebido, retransmitindo dados: {self._format_packet_payload(self.sndpkt)}"
                    )
                    self.retransmissions += 1
                    # Ação: udt_send(sndpkt)
                    self.udt_send(self.sndpkt)
                    # Transição: Estado 2 -> Estado 2 (permanece)
                    continue
                
                # Evento: rdt_rcv(rcvpkt) && isACK(rcvpkt)
                if self.isACK(rcvpkt):
                    self.logger.info(f"[Estado: {self.state}] ACK recebido, pacote confirmado")
                    # Ações: (nenhuma)
                    # Transição: Estado 2 -> Estado 1
                    self.state = self.WAIT_CALL_FROM_ABOVE
                    self.logger.debug(f"Transição: {self.WAIT_ACK_OR_NAK} -> {self.WAIT_CALL_FROM_ABOVE}")
                    self.sndpkt = None
                    return True
                
            except socket.timeout:
                self.logger.warning(
                    f"\n[Estado: {self.state}] Timeout aguardando ACK/NAK, retransmitindo dados: {self._format_packet_payload(self.sndpkt)}"
                )
                self.retransmissions += 1
                # Retransmitir em caso de timeout
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


class RDT20Receiver:
    """
    Receptor rdt2.0 - Implementação do FSM da Figura 3.10b.
    """
    
    # Estado do FSM
    WAIT_CALL_FROM_BELOW = "Esperar chamada de baixo"
    
    def __init__(self, host='localhost', port=5001, channel=None):
        """
        Inicializa o receptor.
        
        Args:
            host: endereço local
            port: porta local
            channel: canal não confiável (usado no simulador)
        """
        self.host = host
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((host, port))
        self.channel = channel
        self.logger = setup_logger('RDT20Receiver')
        self.messages = []
        self.received_count = 0
        self.corrupted_count = 0
        
        # Estado inicial do FSM
        self.state = self.WAIT_CALL_FROM_BELOW
    
    def make_pkt(self, pkt_type):
        """
        Ação: make_pkt(NAK) ou make_pkt(ACK) - cria pacote ACK ou NAK.
        
        Args:
            pkt_type: tipo de pacote (ACK ou NAK)
        
        Returns:
            pacote criado
        """
        return RDT20Packet.create_packet(pkt_type, b'')
    
    def udt_send(self, packet, addr):
        """
        Ação: udt_send(sndpkt) - envia pacote via canal não confiável.
        
        Args:
            packet: pacote a enviar
            addr: endereço de destino
        """
        if self.channel:
            self.channel.send(packet, self.socket, addr)
        else:
            self.socket.sendto(packet, addr)
    
    def extract(self, rcvpkt, data):
        """
        Ação: extract(rcvpkt, data) - extrai dados do pacote recebido.
        
        Args:
            rcvpkt: pacote recebido
            data: variável para armazenar dados extraídos
        
        Returns:
            dados extraídos
        """
        _, extracted_data, _ = RDT20Packet.parse_packet(rcvpkt)
        return extracted_data
    
    def deliver_data(self, data):
        """
        Ação: deliver_data(data) - entrega dados para camada superior.
        
        Args:
            data: dados a entregar
        """
        self.received_count += 1
        self.messages.append(data)
        formatted = RDT20Sender._format_data(data)
        self.logger.info(f"\nDados entregues para camada superior: {len(data)} bytes | Conteúdo: {formatted}")
    
    def corrupt(self, rcvpkt):
        """
        Verifica se o pacote está corrompido.
        
        Args:
            rcvpkt: pacote recebido
        
        Returns:
            True se corrompido, False caso contrário
        """
        _, _, is_valid = RDT20Packet.parse_packet(rcvpkt)
        return not is_valid
    
    def notcorrupt(self, rcvpkt):
        """
        Verifica se o pacote não está corrompido.
        
        Args:
            rcvpkt: pacote recebido
        
        Returns:
            True se não corrompido, False caso contrário
        """
        return not self.corrupt(rcvpkt)
    
    def rdt_rcv(self, timeout=None):
        """
        Método rdt_rcv - Evento de entrada na camada de transporte.
        
        Implementa Estado: "Esperar chamada de baixo"
        
        Eventos processados:
        1. rdt_rcv(rcvpkt) && corrupt(rcvpkt)
           - Ações: sndpkt = make_pkt(NAK), udt_send(sndpkt)
        
        2. rdt_rcv(rcvpkt) && notcorrupt(rcvpkt)
           - Ações: extract(rcvpkt, data), deliver_data(data), sndpkt = make_pkt(ACK), udt_send(sndpkt)
        
        Args:
            timeout: timeout para recepção (None = bloqueante)
        
        Returns:
            dados recebidos ou None
        """
        if timeout:
            self.socket.settimeout(timeout)
        
        try:
            # Evento: rdt_rcv(rcvpkt) - receber pacote do canal
            rcvpkt, addr = self.socket.recvfrom(1024)
            
            # Evento: rdt_rcv(rcvpkt) && corrupt(rcvpkt)
            if self.corrupt(rcvpkt):
                self.logger.warning(f"[Estado: {self.state}] Pacote corrompido recebido, enviando NAK")
                self.corrupted_count += 1
                
                # Ações: sndpkt = make_pkt(NAK), udt_send(sndpkt)
                sndpkt = self.make_pkt(Packet.TYPE_NAK)
                self.udt_send(sndpkt, addr)
                
                # Transição: Estado -> Estado (permanece no mesmo estado)
                return None
            
            # Evento: rdt_rcv(rcvpkt) && notcorrupt(rcvpkt)
            if self.notcorrupt(rcvpkt):
                packet_type, _, _ = RDT20Packet.parse_packet(rcvpkt)
                if packet_type == Packet.TYPE_DATA:
                    # Ação: extract(rcvpkt, data)
                    data = self.extract(rcvpkt, None)
                    formatted = RDT20Sender._format_data(data)
                    self.logger.info(
                        f"\n[Estado: {self.state}] Pacote DATA recebido e válido | Dados: {formatted}"
                    )
                    
                    # Ação: deliver_data(data)
                    self.deliver_data(data)
                    
                    # Ações: sndpkt = make_pkt(ACK), udt_send(sndpkt)
                    sndpkt = self.make_pkt(Packet.TYPE_ACK)
                    self.udt_send(sndpkt, addr)
                    
                    # Transição: Estado -> Estado (permanece no mesmo estado)
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
            'corrupted': self.corrupted_count
        }
    
    def get_state(self):
        """Retorna o estado atual do FSM."""
        return self.state
    
    def close(self):
        """Fecha o socket."""
        self.socket.close()
