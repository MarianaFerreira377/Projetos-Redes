"""
Implementação do protocolo Go-Back-N (GBN).
Referência: Seção 3.4.3, Figuras 3.19, 3.20 e 3.21 - Kurose & Ross

FSM do Remetente (Figura 3.20):
- Estado único: "Esperar"
- Condições iniciais: base = 1, nextseqnum = 1
- Eventos:
  1. rdt_send(data): 
     - Se nextseqnum < base + N: criar e enviar pacote, start_timer se base == nextseqnum, nextseqnum++
     - Senão: refuse_data(data)
  2. rdt_rcv(rcvpkt) && corrupt(rcvpkt): descartar (nenhuma ação)
  3. timeout: retransmitir todos os pacotes [base, nextseqnum-1], start_timer
  4. rdt_rcv(rcvpkt) && notcorrupt(rcvpkt): 
     - base = getacknum(rcvpkt) + 1
     - Se base == nextseqnum: stop_timer
     - Senão: start_timer

FSM do Receptor (Figura 3.21):
- Estado único: "Esperar"
- Condições iniciais: expectedseqnum = 1, sndpkt = make_pkt(0, ACK, checksum)
- Eventos:
  1. rdt_rcv(rcvpkt) && notcorrupt(rcvpkt) && hasseqnum(rcvpkt, expectedseqnum):
     - extract(rcvpkt, data), deliver_data(data)
     - sndpkt = make_pkt(expectedseqnum, ACK, checksum), udt_send(sndpkt)
     - expectedseqnum++
  2. default (qualquer outro caso): udt_send(sndpkt) - reenviar último ACK
"""
import socket
import sys
import os
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.packet import GBNPacket, Packet
from utils.logger import setup_logger


class GBNSender:
    """
    Remetente Go-Back-N - Implementação do FSM da Figura 3.20.
    """
    
    # Estado do FSM
    WAIT = "Esperar"
    
    def __init__(self, host='localhost', port=6000, dest_host='localhost', dest_port=6001, 
                 channel=None, window_size=5, timeout=2.0):
        """
        Inicializa o remetente GBN.
        
        Args:
            host: endereço local
            port: porta local
            dest_host: endereço de destino
            dest_port: porta de destino
            channel: canal não confiável
            window_size: tamanho da janela (N)
            timeout: timeout em segundos
        """
        self.host = host
        self.port = port
        self.dest_addr = (dest_host, dest_port)
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((host, port))
        self.socket.settimeout(0.1)  # Timeout curto para verificar periodicamente
        self.channel = channel
        self.logger = setup_logger('GBNSender')
        
        # Condições iniciais (conforme Figura 3.20)
        # Usando 0-indexado para compatibilidade com a implementação
        self.base = 0  # base = 1 no livro (ajustado para 0-indexado)
        self.nextseqnum = 0  # nextseqnum = 1 no livro (ajustado para 0-indexado)
        self.N = window_size  # Tamanho da janela
        
        # Estruturas de dados
        self.sndpkt = {}  # Dicionário: sndpkt[nextseqnum] = pacote criado
        self.timeout_interval = timeout
        self.timer = None
        self.timer_lock = threading.Lock()
        
        # Estatísticas
        self.retransmissions = 0
        self.start_time = None
        self.bytes_sent = 0
        self.running = True
        
        # Estado do FSM
        self.state = self.WAIT
        
        # Thread para receber ACKs
        self.ack_thread = None
    
    def make_pkt(self, seqnum, data, checksum):
        """
        Ação: make_pkt(nextseqnum, data, checksum) - cria pacote com número de sequência.
        
        Args:
            seqnum: número de sequência
            data: dados
            checksum: checksum (calculado internamente)
        
        Returns:
            pacote criado
        """
        return GBNPacket.create_packet(Packet.TYPE_DATA, seqnum, data)
    
    def udt_send(self, packet):
        """
        Ação: udt_send(sndpkt) - envia pacote via canal não confiável.
        
        Args:
            packet: pacote a enviar
        """
        if self.channel:
            self.channel.send(packet, self.socket, self.dest_addr)
        else:
            self.socket.sendto(packet, self.dest_addr)
    
    def start_timer(self):
        """
        Ação: start_timer() - inicia o temporizador.
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
    
    def corrupt(self, rcvpkt):
        """Verifica se o pacote está corrompido."""
        _, _, _, is_valid = GBNPacket.parse_packet(rcvpkt)
        return not is_valid
    
    def notcorrupt(self, rcvpkt):
        """Verifica se o pacote não está corrompido."""
        return not self.corrupt(rcvpkt)
    
    def getacknum(self, rcvpkt):
        """
        Extrai o número de ACK do pacote recebido.
        
        Args:
            rcvpkt: pacote recebido
        
        Returns:
            número de sequência do ACK
        """
        _, ack_num, _, _ = GBNPacket.parse_packet(rcvpkt)
        return ack_num
    
    def refuse_data(self, data):
        """
        Ação: refuse_data(data) - recusa dados quando janela está cheia.
        
        Args:
            data: dados a serem recusados
        """
        self.logger.warning(f"[Estado: {self.state}] Janela cheia, recusando dados (janela={self.N})")
        # Em implementação real, poderia bufferizar ou retornar erro
    
    def rdt_send(self, data):
        """
        Método rdt_send - Evento de entrada na camada de transporte.
        
        Implementa evento: rdt_send(data) conforme Figura 3.20.
        
        Se nextseqnum < base + N:
          - sndpkt[nextseqnum] = make_pkt(nextseqnum, data, checksum)
          - udt_send(sndpkt[nextseqnum])
          - if (base == nextseqnum): start_timer
          - nextseqnum++
        Senão:
          - refuse_data(data)
        """
        if isinstance(data, str):
            data = data.encode('utf-8')
        
        if self.start_time is None:
            self.start_time = time.time()
        
        # Verificar se janela está cheia
        if self.nextseqnum < self.base + self.N:
            # Janela não está cheia, pode enviar
            seqnum = self.nextseqnum
            
            # Ação: sndpkt[nextseqnum] = make_pkt(nextseqnum, data, checksum)
            self.sndpkt[seqnum] = self.make_pkt(seqnum, data, None)
            
            # Ação: udt_send(sndpkt[nextseqnum])
            self.udt_send(self.sndpkt[seqnum])
            
            self.logger.info(f"[Estado: {self.state}] Pacote seq={seqnum} enviado: {len(data)} bytes (base={self.base}, nextseqnum={self.nextseqnum}, N={self.N})")
            self.bytes_sent += len(data)
            
            # Ação: if (base == nextseqnum): start_timer
            if self.base == self.nextseqnum:
                self.start_timer()
            
            # Ação: nextseqnum++
            self.nextseqnum += 1
            
            # Iniciar thread de recepção de ACKs se necessário
            self._receive_acks()
            
            return True
        else:
            # Janela cheia
            self.refuse_data(data)
            return False
    
    def _timeout_handler(self):
        """
        Handler chamado quando timer expira (evento: timeout).
        
        Ações:
        - start_timer
        - udt_send(sndpkt[base])
        - udt_send(sndpkt[base+1])
        - ...
        - udt_send(sndpkt[nextseqnum-1])
        """
        self.logger.warning(f"[Estado: {self.state}] Timeout ocorreu, retransmitindo pacotes de {self.base} até {self.nextseqnum-1}")
        
        # Retransmitir todos os pacotes na janela [base, nextseqnum-1]
        for seq in range(self.base, self.nextseqnum):
            if seq in self.sndpkt:
                self.udt_send(self.sndpkt[seq])
                self.retransmissions += 1
                self.logger.debug(f"Retransmitido pacote seq={seq}")
        
        # Ação: start_timer
        self.start_timer()
    
    def _receive_acks(self):
        """Inicia thread para receber ACKs se necessário."""
        if self.ack_thread is None or not self.ack_thread.is_alive():
            self.ack_thread = threading.Thread(target=self._ack_loop, daemon=True)
            self.ack_thread.start()
    
    def _ack_loop(self):
        """
        Loop para receber e processar ACKs.
        
        Processa eventos conforme Figura 3.20:
        - rdt_rcv(rcvpkt) && corrupt(rcvpkt): nenhuma ação
        - rdt_rcv(rcvpkt) && notcorrupt(rcvpkt): base = getacknum(rcvpkt) + 1, atualizar timer
        """
        while self.running:
            try:
                # Evento: rdt_rcv(rcvpkt)
                rcvpkt, addr = self.socket.recvfrom(1024)
                packet_type, _, _, is_valid = GBNPacket.parse_packet(rcvpkt)
                
                if packet_type != Packet.TYPE_ACK:
                    continue
                
                # Evento: rdt_rcv(rcvpkt) && corrupt(rcvpkt)
                if self.corrupt(rcvpkt):
                    # Ações: nenhuma (descartar)
                    self.logger.debug(f"[Estado: {self.state}] ACK corrompido recebido, descartando")
                    continue
                
                # Evento: rdt_rcv(rcvpkt) && notcorrupt(rcvpkt)
                if self.notcorrupt(rcvpkt):
                    # Ação: base = getacknum(rcvpkt) + 1
                    ack_num = self.getacknum(rcvpkt)
                    old_base = self.base
                    self.base = ack_num + 1
                    
                    self.logger.info(f"[Estado: {self.state}] ACK cumulativo recebido: ACK {ack_num}, base atualizado {old_base} -> {self.base}")
                    
                    # Remover pacotes confirmados
                    seqs_to_remove = [s for s in self.sndpkt.keys() if s < self.base]
                    for s in seqs_to_remove:
                        del self.sndpkt[s]
                    
                    # Ação: if (base == nextseqnum): stop_timer
                    if self.base == self.nextseqnum:
                        self.stop_timer()
                    else:
                        # Senão: start_timer
                        self.start_timer()
                    
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    self.logger.error(f"Erro ao receber ACK: {e}")
    
    def send(self, data):
        """Alias para rdt_send para compatibilidade."""
        return self.rdt_send(data)
    
    def wait_for_all_acks(self, timeout=30):
        """Aguarda todos os ACKs serem recebidos."""
        start = time.time()
        while self.base < self.nextseqnum:
            if time.time() - start > timeout:
                self.logger.warning("Timeout aguardando todos os ACKs")
                break
            time.sleep(0.1)
    
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
            'throughput_mbps': throughput / 1_000_000,
            'window_size': self.N,
            'base': self.base,
            'nextseqnum': self.nextseqnum
        }
    
    def get_state(self):
        """Retorna o estado atual do FSM."""
        return self.state
    
    def close(self):
        """Fecha o socket."""
        self.running = False
        self.stop_timer()
        if self.ack_thread:
            self.ack_thread.join(timeout=1)
        self.socket.close()


class GBNReceiver:
    """
    Receptor Go-Back-N - Implementação do FSM da Figura 3.21.
    """
    
    # Estado do FSM
    WAIT = "Esperar"
    
    def __init__(self, host='localhost', port=6001, channel=None):
        """
        Inicializa o receptor GBN.
        
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
        self.logger = setup_logger('GBNReceiver')
        
        # Condições iniciais (conforme Figura 3.21)
        # Usando 0-indexado para compatibilidade
        self.expectedseqnum = 0  # expectedseqnum = 1 no livro (ajustado para 0-indexado)
        
        # Ação inicial: sndpkt = make_pkt(0, ACK, checksum)
        self.sndpkt = self.make_pkt(0, Packet.TYPE_ACK, None)
        
        # Estado do FSM
        self.state = self.WAIT
        
        # Estatísticas
        self.messages = []
        self.received_count = 0
        self.corrupted_count = 0
        self.out_of_order_count = 0
    
    def make_pkt(self, seqnum, ack_type, checksum):
        """
        Ação: make_pkt(expectedseqnum, ACK, checksum) - cria pacote ACK.
        
        Args:
            seqnum: número de sequência do ACK
            ack_type: tipo (ACK)
            checksum: checksum (calculado internamente)
        
        Returns:
            pacote ACK criado
        """
        return GBNPacket.create_packet(ack_type, seqnum, b'')
    
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
    
    def corrupt(self, rcvpkt):
        """Verifica se o pacote está corrompido."""
        _, _, _, is_valid = GBNPacket.parse_packet(rcvpkt)
        return not is_valid
    
    def notcorrupt(self, rcvpkt):
        """Verifica se o pacote não está corrompido."""
        return not self.corrupt(rcvpkt)
    
    def hasseqnum(self, rcvpkt, expectedseqnum):
        """
        Verifica se o pacote tem o número de sequência esperado.
        
        Args:
            rcvpkt: pacote recebido
            expectedseqnum: número de sequência esperado
        
        Returns:
            True se o pacote tem o número de sequência esperado
        """
        _, seq_num, _, is_valid = GBNPacket.parse_packet(rcvpkt)
        return is_valid and seq_num == expectedseqnum
    
    def extract(self, rcvpkt, data):
        """
        Ação: extract(rcvpkt, data) - extrai dados do pacote.
        
        Args:
            rcvpkt: pacote recebido
            data: variável para armazenar dados (não usada)
        
        Returns:
            dados extraídos
        """
        _, _, extracted_data, _ = GBNPacket.parse_packet(rcvpkt)
        return extracted_data
    
    def deliver_data(self, data):
        """
        Ação: deliver_data(data) - entrega dados para camada superior.
        
        Args:
            data: dados a entregar
        """
        self.received_count += 1
        self.messages.append(data)
        self.logger.info(f"Dados entregues para camada superior: {len(data)} bytes")
    
    def rdt_rcv(self, timeout=None):
        """
        Método rdt_rcv - Evento de entrada na camada de transporte.
        
        Implementa FSM conforme Figura 3.21.
        
        Evento 1: rdt_rcv(rcvpkt) && notcorrupt(rcvpkt) && hasseqnum(rcvpkt, expectedseqnum)
          - extract(rcvpkt, data)
          - deliver_data(data)
          - sndpkt = make_pkt(expectedseqnum, ACK, checksum)
          - udt_send(sndpkt)
          - expectedseqnum++
        
        Evento 2: default (qualquer outro caso)
          - udt_send(sndpkt) - reenviar último ACK
        """
        if timeout:
            self.socket.settimeout(timeout)
        
        try:
            # Evento: rdt_rcv(rcvpkt)
            rcvpkt, addr = self.socket.recvfrom(1024)
            packet_type, seq_num, _, is_valid = GBNPacket.parse_packet(rcvpkt)
            
            if packet_type != Packet.TYPE_DATA:
                return None
            
            # Evento: rdt_rcv(rcvpkt) && notcorrupt(rcvpkt) && hasseqnum(rcvpkt, expectedseqnum)
            if self.notcorrupt(rcvpkt) and self.hasseqnum(rcvpkt, self.expectedseqnum):
                self.logger.info(f"[Estado: {self.state}] Pacote seq={self.expectedseqnum} correto recebido")
                
                # Ação: extract(rcvpkt, data)
                data = self.extract(rcvpkt, None)
                
                # Ação: deliver_data(data)
                self.deliver_data(data)
                
                # Ações: sndpkt = make_pkt(expectedseqnum, ACK, checksum), udt_send(sndpkt)
                self.sndpkt = self.make_pkt(self.expectedseqnum, Packet.TYPE_ACK, None)
                self.udt_send(self.sndpkt, addr)
                
                # Ação: expectedseqnum++
                self.expectedseqnum += 1
                
                return data
            
            else:
                # Evento: default (pacote corrompido ou fora de ordem)
                if self.corrupt(rcvpkt):
                    self.logger.warning(f"[Estado: {self.state}] Pacote corrompido recebido, reenviando ACK")
                    self.corrupted_count += 1
                else:
                    self.logger.warning(f"[Estado: {self.state}] Pacote fora de ordem recebido (seq={seq_num}, esperado={self.expectedseqnum}), descartando e reenviando ACK")
                    self.out_of_order_count += 1
                
                # Ação: udt_send(sndpkt) - reenviar último ACK
                self.udt_send(self.sndpkt, addr)
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
            'out_of_order': self.out_of_order_count,
            'expectedseqnum': self.expectedseqnum
        }
    
    def get_state(self):
        """Retorna o estado atual do FSM."""
        return self.state
    
    def close(self):
        """Fecha o socket."""
        self.socket.close()
