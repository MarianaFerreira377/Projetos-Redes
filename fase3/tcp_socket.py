"""
Implementação de TCP Simplificado sobre UDP.
Referência: Seção 3.5 - Kurose & Ross
"""
import socket
import sys
import os
import threading
import time
import random
import queue
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.packet import TCPSegment
from utils.logger import setup_logger


class SimpleTCPSocket:
    """
    Socket TCP simplificado sobre UDP.
    Implementa: three-way handshake, transferência confiável, controle de fluxo,
    retransmissão adaptativa e encerramento de conexão.
    """
    
    # Estados da conexão
    CLOSED = 'CLOSED'
    LISTEN = 'LISTEN'
    SYN_SENT = 'SYN_SENT'
    SYN_RCVD = 'SYN_RCVD'
    ESTABLISHED = 'ESTABLISHED'
    FIN_WAIT_1 = 'FIN_WAIT_1'
    FIN_WAIT_2 = 'FIN_WAIT_2'
    CLOSE_WAIT = 'CLOSE_WAIT'
    CLOSING = 'CLOSING'
    TIME_WAIT = 'TIME_WAIT'
    LAST_ACK = 'LAST_ACK'
    
    # Tamanhos padrão
    DEFAULT_RECV_WINDOW = 4096
    MAX_SEGMENT_SIZE = 1024
    INITIAL_TIMEOUT = 2.0
    
    def __init__(self, port, host='localhost'):
        """
        Inicializa socket TCP simplificado.
        
        Args:
            port: porta local
            host: endereço local
        """
        self.port = port
        self.host = host
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.bind((host, port))
        self.udp_socket.settimeout(0.1)
        
        # Estado da conexão
        self.state = self.CLOSED
        
        # Números de sequência e ACK
        self.seq_num = random.randint(0, 10000)  # ISN (Initial Sequence Number)
        self.ack_num = 0
        self.send_base = self.seq_num  # Base do buffer de envio
        
        # Buffers
        self.send_buffer = deque()  # Dados a serem enviados
        self.recv_buffer = deque()  # Dados recebidos
        self.recv_buffer_lock = threading.Lock()
        self.send_buffer_lock = threading.Lock()
        
        # Controle de fluxo
        self.recv_window = self.DEFAULT_RECV_WINDOW
        self.send_window = self.DEFAULT_RECV_WINDOW
        
        # Controle de tempo (RTT)
        self.estimated_rtt = 1.0
        self.dev_rtt = 0.5
        self.timeout_interval = self.INITIAL_TIMEOUT
        
        # Dados do peer
        self.peer_address = None
        self.peer_port = None
        
        # Timers
        self.timers = {}  # {seq_num: timer}
        self.timer_lock = threading.Lock()
        
        # Rastreamento de RTT
        self.send_times = {}  # {seq_num: timestamp} - para calcular SampleRTT
        self.unacked_segments = {}  # {seq_num: data} - segmentos aguardando ACK
        
        # Threads
        self.receive_thread = None
        self.running = False
        
        # Estatísticas
        self.retransmissions = 0
        self.bytes_sent = 0
        self.bytes_received = 0
        self.start_time = None
        
        # Locks
        self.state_lock = threading.Lock()
        
        self.logger = setup_logger('SimpleTCPSocket')
        self._send_interceptor = None
    
    def set_send_interceptor(self, interceptor):
        """
        Define função para interceptar envios UDP (usado em testes).
        
        interceptor(data, dest, send_func) deve decidir se envia ou descarta.
        """
        self._send_interceptor = interceptor
    
    def _udp_send(self, data, dest):
        """Envia segmento via UDP aplicando interceptor se configurado."""
        if self._send_interceptor:
            return self._send_interceptor(data, dest, self.udp_socket.sendto)
        return self.udp_socket.sendto(data, dest)
    
    def connect(self, dest_address):
        """
        Inicia conexão com three-way handshake.
        
        Args:
            dest_address: tupla (host, port)
        """
        with self.state_lock:
            if self.state != self.CLOSED:
                raise Exception("Socket já está em uso")
            self.state = self.SYN_SENT
            self.peer_address = dest_address[0]
            self.peer_port = dest_address[1]
        
        # Iniciar thread de recepção
        self.running = True
        self.receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
        self.receive_thread.start()
        
        # Enviar SYN
        self.logger.info(f"Iniciando conexão com {dest_address}")
        segment = TCPSegment.create_segment(
            src_port=self.port,
            dst_port=self.peer_port,
            seq_num=self.seq_num,
            ack_num=0,
            flags=TCPSegment.FLAG_SYN,
            window_size=self.recv_window,
            data=b''
        )
        self._udp_send(segment, dest_address)
        self.logger.info(f"SYN enviado (seq={self.seq_num})")
        
        # Aguardar SYN-ACK (com timeout)
        start_time = time.time()
        while self.state == self.SYN_SENT:
            if time.time() - start_time > 10:
                self.state = self.CLOSED
                raise Exception("Timeout no estabelecimento de conexão")
            time.sleep(0.1)
        
        if self.state != self.ESTABLISHED:
            raise Exception(f"Falha ao estabelecer conexão. Estado: {self.state}")
        
        self.logger.info("Conexão estabelecida")
    
    def listen(self, backlog=5):
        """
        Coloca socket em modo de escuta.
        
        Args:
            backlog: número máximo de conexões pendentes (não usado na versão simplificada)
        """
        with self.state_lock:
            if self.state != self.CLOSED:
                raise Exception("Socket já está em uso")
            self.state = self.LISTEN
        
        self.running = True
        self.receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
        self.receive_thread.start()
        
        self.logger.info(f"Socket em modo de escuta na porta {self.port}")
    
    def accept(self):
        """
        Aceita conexão entrante (completa handshake).
        
        Returns:
            socket conectado
        """
        # Aguardar SYN
        while self.state == self.LISTEN:
            time.sleep(0.1)
        
        if self.state == self.SYN_RCVD:
            # Aguardar ACK final
            start_time = time.time()
            while self.state == self.SYN_RCVD:
                if time.time() - start_time > 10:
                    raise Exception("Timeout aguardando ACK final")
                time.sleep(0.1)
        
        if self.state != self.ESTABLISHED:
            raise Exception(f"Falha ao aceitar conexão. Estado: {self.state}")
        
        self.logger.info("Conexão aceita")
        return self
    
    def send(self, data):
        """
        Envia dados (pode bloquear se buffer cheio).
        
        Args:
            data: bytes a enviar
        
        Returns:
            número de bytes enviados
        """
        if isinstance(data, str):
            data = data.encode('utf-8')
        
        if self.state != self.ESTABLISHED:
            raise Exception("Socket não está conectado")
        
        if self.start_time is None:
            self.start_time = time.time()
        
        # Adicionar ao buffer de envio
        with self.send_buffer_lock:
            self.send_buffer.append(data)
            self.bytes_sent += len(data)
        
        # Enviar dados disponíveis
        self._send_data()
        
        return len(data)
    
    def _send_data(self):
        """Envia dados do buffer respeitando a janela de envio."""
        with self.send_buffer_lock:
            available_window = self.send_window - (self.seq_num - self.send_base)
            
            while self.send_buffer and available_window > 0:
                data = self.send_buffer.popleft()
                segment_size = min(len(data), self.MAX_SEGMENT_SIZE, available_window)
                segment_data = data[:segment_size]
                
                # Criar segmento
                current_seq = self.seq_num
                segment = TCPSegment.create_segment(
                    src_port=self.port,
                    dst_port=self.peer_port,
                    seq_num=current_seq,
                    ack_num=self.ack_num,
                    flags=TCPSegment.FLAG_ACK,
                    window_size=self.recv_window,
                    data=segment_data
                )
                
                # Enviar
                self._udp_send(segment, (self.peer_address, self.peer_port))
                self.logger.debug(f"Segmento enviado: seq={current_seq}, len={len(segment_data)}")
                
                # Guardar cópia para possível retransmissão
                self.unacked_segments[current_seq] = segment_data
                
                # Armazenar timestamp para cálculo de RTT
                self.send_times[current_seq] = time.time()
                
                # Iniciar timer
                self._start_timer(current_seq)
                
                # Atualizar sequência
                self.seq_num += len(segment_data)
                available_window -= len(segment_data)
                
                # Se sobrou dados, recolocar no buffer
                if len(data) > segment_size:
                    self.send_buffer.appendleft(data[segment_size:])
    
    def recv(self, buffer_size):
        """
        Recebe dados do buffer de recepção.
        
        Args:
            buffer_size: tamanho máximo do buffer
        
        Returns:
            dados recebidos
        """
        if self.state != self.ESTABLISHED and self.state != self.CLOSE_WAIT:
            return b''
        
        timeout_start = time.time()
        while True:
            with self.recv_buffer_lock:
                if self.recv_buffer:
                    chunks = []
                    total = 0
                    while self.recv_buffer and total < buffer_size:
                        chunk = self.recv_buffer.popleft()
                        needed = buffer_size - total
                        if len(chunk) <= needed:
                            chunks.append(chunk)
                            total += len(chunk)
                        else:
                            chunks.append(chunk[:needed])
                            total += needed
                            self.recv_buffer.appendleft(chunk[needed:])
                    data = b''.join(chunks)
                    self.bytes_received += len(data)
                    return data
            
            if time.time() - timeout_start > 5:
                return b''
            time.sleep(0.1)
    
    def _receive_loop(self):
        """Thread que recebe segmentos UDP e processa."""
        while self.running:
            try:
                segment, addr = self.udp_socket.recvfrom(2048)
                parsed = TCPSegment.parse_segment(segment)
                
                if not parsed:
                    continue
                
                # Atualizar endereço do peer se necessário
                if not self.peer_address:
                    self.peer_address = addr[0]
                    self.peer_port = parsed['dst_port']
                
                self._process_segment(parsed, addr)
                
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    self.logger.error(f"Erro no loop de recepção: {e}")
    
    def _process_segment(self, segment, addr):
        """Processa um segmento TCP recebido."""
        flags = segment['flags']
        seq_num = segment['seq_num']
        ack_num = segment['ack_num']
        data = segment['data']
        window_size = segment['window_size']
        
        # Atualizar janela de envio
        self.send_window = window_size
        
        # Processar flags
        if flags & TCPSegment.FLAG_SYN:
            self._handle_syn(segment, addr)
        elif flags & TCPSegment.FLAG_FIN:
            self._handle_fin(segment, addr)
        elif flags & TCPSegment.FLAG_ACK:
            self._handle_ack(ack_num)
        
        # Processar dados
        if data and (flags & TCPSegment.FLAG_ACK):
            self._handle_data(seq_num, data)
    
    def _handle_syn(self, segment, addr):
        """Trata segmento SYN."""
        if self.state == self.LISTEN:
            # Recebido SYN, enviar SYN-ACK
            self.peer_address = addr[0]
            self.peer_port = segment['src_port']
            self.ack_num = segment['seq_num'] + 1
            self.seq_num = random.randint(0, 10000)
            
            syn_ack = TCPSegment.create_segment(
                src_port=self.port,
                dst_port=self.peer_port,
                seq_num=self.seq_num,
                ack_num=self.ack_num,
                flags=TCPSegment.FLAG_SYN | TCPSegment.FLAG_ACK,
                window_size=self.recv_window,
                data=b''
            )
            self._udp_send(syn_ack, (self.peer_address, self.peer_port))
            
            with self.state_lock:
                self.state = self.SYN_RCVD
            self.logger.info(f"SYN-ACK enviado (seq={self.seq_num}, ack={self.ack_num})")
        
        elif self.state == self.SYN_SENT:
            # Recebido SYN-ACK, enviar ACK
            self.ack_num = segment['seq_num'] + 1
            self.seq_num += 1  # Incrementar seq_num após enviar SYN
            
            ack = TCPSegment.create_segment(
                src_port=self.port,
                dst_port=self.peer_port,
                seq_num=self.seq_num,
                ack_num=self.ack_num,
                flags=TCPSegment.FLAG_ACK,
                window_size=self.recv_window,
                data=b''
            )
            self._udp_send(ack, (self.peer_address, self.peer_port))
            
            with self.state_lock:
                self.state = self.ESTABLISHED
            self.logger.info(f"ACK final enviado, conexão estabelecida")
    
    def _handle_ack(self, ack_num):
        """Trata ACK recebido."""
        if self.state == self.SYN_RCVD:
            expected_ack = self.seq_num + 1
            if ack_num >= expected_ack:
                with self.state_lock:
                    self.state = self.ESTABLISHED
                self.seq_num = ack_num
                self.send_base = ack_num
                self.logger.info("ACK final recebido pelo servidor, conexão estabelecida")
                return
        
        if ack_num > self.send_base:
            # Calcular SampleRTT para o último segmento confirmado
            # O ACK confirma todos os bytes até ack_num-1
            # Procurar o timestamp do segmento mais recente que foi completamente confirmado
            current_time = time.time()
            for seq in sorted(self.send_times.keys(), reverse=True):
                if seq < ack_num and seq in self.send_times:
                    # Calcular SampleRTT
                    sample_rtt = current_time - self.send_times[seq]
                    if sample_rtt > 0:
                        # Atualizar estimativa de RTT
                        self._update_rtt(sample_rtt)
                        self.logger.debug(f"RTT atualizado: SampleRTT={sample_rtt:.3f}s, EstimatedRTT={self.estimated_rtt:.3f}s, Timeout={self.timeout_interval:.3f}s")
                    # Remover timestamps confirmados
                    seqs_to_remove = [s for s in self.send_times.keys() if s < ack_num]
                    for s in seqs_to_remove:
                        del self.send_times[s]
                    break
            
            # Atualizar base do buffer de envio
            old_base = self.send_base
            self.send_base = ack_num
            
            # Cancelar timers dos pacotes confirmados
            with self.timer_lock:
                seqs_to_remove = [s for s in self.timers.keys() if s < ack_num]
                for s in seqs_to_remove:
                    if s in self.timers:
                        self.timers[s].cancel()
                        del self.timers[s]
            
            self.logger.debug(f"ACK recebido: ack={ack_num}, base atualizado {old_base} -> {self.send_base}")
            
            # Remover segmentos confirmados do buffer de não confirmados
            with self.send_buffer_lock:
                confirmed = [seq for seq, data in self.unacked_segments.items() if seq + len(data) <= ack_num]
                for seq in confirmed:
                    self.unacked_segments.pop(seq, None)
            
            # Tentar enviar mais dados
            self._send_data()
    
    def _handle_data(self, seq_num, data):
        """Trata dados recebidos."""
        if seq_num == self.ack_num:
            # Dados em ordem
            with self.recv_buffer_lock:
                self.recv_buffer.append(data)
            self.ack_num += len(data)
            
            # Enviar ACK
            ack = TCPSegment.create_segment(
                src_port=self.port,
                dst_port=self.peer_port,
                seq_num=self.seq_num,
                ack_num=self.ack_num,
                flags=TCPSegment.FLAG_ACK,
                window_size=self.recv_window,
                data=b''
            )
            self._udp_send(ack, (self.peer_address, self.peer_port))
            self.logger.debug(f"Dados recebidos: {len(data)} bytes, ACK enviado (ack={self.ack_num})")
        else:
            # Dados fora de ordem (simplificado: descarta)
            self.logger.warning(f"Dados fora de ordem recebidos (seq={seq_num}, esperado={self.ack_num})")
            # Reenviar ACK do último byte recebido em ordem
            ack = TCPSegment.create_segment(
                src_port=self.port,
                dst_port=self.peer_port,
                seq_num=self.seq_num,
                ack_num=self.ack_num,
                flags=TCPSegment.FLAG_ACK,
                window_size=self.recv_window,
                data=b''
            )
            self._udp_send(ack, (self.peer_address, self.peer_port))
    
    def _handle_fin(self, segment, addr):
        """Trata segmento FIN."""
        if self.state == self.ESTABLISHED:
            # Recebido FIN, enviar ACK
            self.ack_num = segment['seq_num'] + 1
            
            ack = TCPSegment.create_segment(
                src_port=self.port,
                dst_port=self.peer_port,
                seq_num=self.seq_num,
                ack_num=self.ack_num,
                flags=TCPSegment.FLAG_ACK,
                window_size=self.recv_window,
                data=b''
            )
            self.udp_socket.sendto(ack, (self.peer_address, self.peer_port))
            
            with self.state_lock:
                self.state = self.CLOSE_WAIT
            self.logger.info("FIN recebido, enviado ACK")
    
    def close(self):
        """Fecha conexão (four-way handshake)."""
        if self.state == self.CLOSED:
            return
        
        if self.state == self.ESTABLISHED:
            # Enviar FIN
            fin = TCPSegment.create_segment(
                src_port=self.port,
                dst_port=self.peer_port,
                seq_num=self.seq_num,
                ack_num=self.ack_num,
                flags=TCPSegment.FLAG_FIN | TCPSegment.FLAG_ACK,
                window_size=self.recv_window,
                data=b''
            )
            self._udp_send(fin, (self.peer_address, self.peer_port))
            
            with self.state_lock:
                self.state = self.FIN_WAIT_1
            self.logger.info("FIN enviado")
            
            # Aguardar ACK
            start_time = time.time()
            while self.state == self.FIN_WAIT_1:
                if time.time() - start_time > 10:
                    break
                time.sleep(0.1)
            
            # Aguardar FIN
            if self.state == self.FIN_WAIT_2:
                start_time = time.time()
                while self.state == self.FIN_WAIT_2:
                    if time.time() - start_time > 10:
                        break
                    time.sleep(0.1)
        
        elif self.state == self.CLOSE_WAIT:
            # Enviar FIN
            fin = TCPSegment.create_segment(
                src_port=self.port,
                dst_port=self.peer_port,
                seq_num=self.seq_num,
                ack_num=self.ack_num,
                flags=TCPSegment.FLAG_FIN | TCPSegment.FLAG_ACK,
                window_size=self.recv_window,
                data=b''
            )
            self._udp_send(fin, (self.peer_address, self.peer_port))
            
            with self.state_lock:
                self.state = self.LAST_ACK
        
        # Aguardar encerramento
        time.sleep(1)
        
        self.running = False
        with self.state_lock:
            self.state = self.CLOSED
        
        # Cancelar todos os timers
        with self.timer_lock:
            for timer in self.timers.values():
                timer.cancel()
            self.timers.clear()
        
        self.udp_socket.close()
        self.logger.info("Conexão encerrada")
    
    def _start_timer(self, seq_num):
        """Inicia timer para um segmento."""
        with self.timer_lock:
            if seq_num in self.timers:
                self.timers[seq_num].cancel()
            
            timer = threading.Timer(self.timeout_interval, self._timeout_handler, args=(seq_num,))
            timer.start()
            self.timers[seq_num] = timer
    
    def _timeout_handler(self, seq_num):
        """Handler chamado quando timer expira."""
        self.logger.warning(f"Timeout para segmento seq={seq_num}, retransmitindo...")
        self.retransmissions += 1
        
        # Não atualizar RTT em caso de timeout (timeout indica que o segmento foi perdido)
        # Remover timestamp antigo (se existir) para evitar cálculos incorretos
        if seq_num in self.send_times:
            # Não remover, mas marcar para não usar esse SampleRTT
            # (em implementação mais sofisticada, poderia usar Karn's algorithm)
            pass
        
        # Retransmitir todos os segmentos não confirmados a partir de seq_num (Go-Back-N)
        with self.send_buffer_lock:
            pending = [(seq, data) for seq, data in self.unacked_segments.items() if seq >= seq_num]
        
        if not pending:
            return
        
        for seq, data in sorted(pending):
            segment = TCPSegment.create_segment(
                src_port=self.port,
                dst_port=self.peer_port,
                seq_num=seq,
                ack_num=self.ack_num,
                flags=TCPSegment.FLAG_ACK,
                window_size=self.recv_window,
                data=data
            )
            self._udp_send(segment, (self.peer_address, self.peer_port))
            self.logger.debug(f"Segmento retransmitido: seq={seq}, len={len(data)}")
            self.send_times[seq] = time.time()
            self._start_timer(seq)
    
    def _calculate_timeout(self):
        """Calcula timeout baseado em RTT."""
        return self.estimated_rtt + 4 * self.dev_rtt
    
    def _update_rtt(self, sample_rtt):
        """Atualiza estimativa de RTT."""
        self.estimated_rtt = 0.875 * self.estimated_rtt + 0.125 * sample_rtt
        self.dev_rtt = 0.75 * self.dev_rtt + 0.25 * abs(sample_rtt - self.estimated_rtt)
        self.timeout_interval = self._calculate_timeout()
    
    def get_stats(self):
        """Retorna estatísticas da conexão."""
        end_time = time.time()
        total_time = end_time - self.start_time if self.start_time else 0
        throughput_sent = (self.bytes_sent * 8) / total_time if total_time > 0 else 0
        throughput_recv = (self.bytes_received * 8) / total_time if total_time > 0 else 0
        
        return {
            'retransmissions': self.retransmissions,
            'bytes_sent': self.bytes_sent,
            'bytes_received': self.bytes_received,
            'total_time': total_time,
            'throughput_sent_mbps': throughput_sent / 1_000_000,
            'throughput_recv_mbps': throughput_recv / 1_000_000,
            'estimated_rtt': self.estimated_rtt,
            'timeout_interval': self.timeout_interval
        }

