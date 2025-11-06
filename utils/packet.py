"""
Utilitários para criação e manipulação de pacotes.
Suporta diferentes formatos de pacote para as fases RDT.
"""
import struct
import hashlib


class Packet:
    """Classe base para pacotes de rede."""
    
    # Tipos de pacote
    TYPE_DATA = 0
    TYPE_ACK = 1
    TYPE_NAK = 2
    TYPE_SYN = 3
    TYPE_SYN_ACK = 4
    TYPE_FIN = 5
    
    @staticmethod
    def calculate_checksum(data):
        """Calcula checksum simples usando MD5."""
        return hashlib.md5(data).digest()[:4]
    
    @staticmethod
    def verify_checksum(data, checksum):
        """Verifica checksum do pacote."""
        calculated = Packet.calculate_checksum(data)
        return calculated == checksum


class RDT20Packet(Packet):
    """Pacote para rdt2.0: Tipo + Checksum + Dados."""
    
    FORMAT = '!B4s'  # 1 byte tipo + 4 bytes checksum
    
    @staticmethod
    def create_packet(packet_type, data):
        """Cria um pacote rdt2.0."""
        # Calcula checksum dos dados
        checksum = Packet.calculate_checksum(data)
        # Empacota cabeçalho
        header = struct.pack(RDT20Packet.FORMAT, packet_type, checksum)
        return header + data
    
    @staticmethod
    def parse_packet(packet):
        """Parseia um pacote rdt2.0."""
        if len(packet) < 5:
            return None, None, None
        
        header_size = struct.calcsize(RDT20Packet.FORMAT)
        packet_type, checksum = struct.unpack(RDT20Packet.FORMAT, packet[:header_size])
        data = packet[header_size:]
        
        # Verifica checksum
        is_valid = Packet.verify_checksum(data, checksum)
        
        return packet_type, data, is_valid


class RDT21Packet(Packet):
    """Pacote para rdt2.1 e rdt3.0: Tipo + SeqNum + Checksum + Dados."""
    
    FORMAT = '!BB4s'  # 1 byte tipo + 1 byte seqnum + 4 bytes checksum
    
    @staticmethod
    def create_packet(packet_type, seq_num, data):
        """Cria um pacote rdt2.1/3.0."""
        checksum = Packet.calculate_checksum(data)
        header = struct.pack(RDT21Packet.FORMAT, packet_type, seq_num, checksum)
        return header + data
    
    @staticmethod
    def parse_packet(packet):
        """Parseia um pacote rdt2.1/3.0."""
        if len(packet) < 6:
            return None, None, None, None
        
        header_size = struct.calcsize(RDT21Packet.FORMAT)
        packet_type, seq_num, checksum = struct.unpack(RDT21Packet.FORMAT, packet[:header_size])
        data = packet[header_size:]
        
        is_valid = Packet.verify_checksum(data, checksum)
        
        return packet_type, seq_num, data, is_valid


class GBNPacket(Packet):
    """Pacote para Go-Back-N: Tipo + SeqNum (4 bytes) + Checksum + Dados."""
    
    FORMAT = '!BI4s'  # 1 byte tipo + 4 bytes seqnum + 4 bytes checksum
    
    @staticmethod
    def create_packet(packet_type, seq_num, data):
        """Cria um pacote GBN."""
        checksum = Packet.calculate_checksum(data)
        header = struct.pack(GBNPacket.FORMAT, packet_type, seq_num, checksum)
        return header + data
    
    @staticmethod
    def parse_packet(packet):
        """Parseia um pacote GBN."""
        if len(packet) < 9:
            return None, None, None, None
        
        header_size = struct.calcsize(GBNPacket.FORMAT)
        packet_type, seq_num, checksum = struct.unpack(GBNPacket.FORMAT, packet[:header_size])
        data = packet[header_size:]
        
        is_valid = Packet.verify_checksum(data, checksum)
        
        return packet_type, seq_num, data, is_valid


class TCPSegment:
    """Segmento TCP simplificado."""
    
    FORMAT = '!HHIIBBHHH'  # Ports, Seq, Ack, HeaderLen, Flags, Window, Checksum, Urgent
    
    # Flags TCP
    FLAG_URG = 0x20
    FLAG_ACK = 0x10
    FLAG_PSH = 0x08
    FLAG_RST = 0x04
    FLAG_SYN = 0x02
    FLAG_FIN = 0x01
    
    @staticmethod
    def create_segment(src_port, dst_port, seq_num, ack_num, flags, window_size, data=b''):
        """Cria um segmento TCP."""
        header_len = 20  # 20 bytes de cabeçalho
        flags_byte = flags
        checksum = 0  # Simplificado - em TCP real é mais complexo
        urgent_ptr = 0
        
        header = struct.pack(TCPSegment.FORMAT,
                           src_port, dst_port,
                           seq_num, ack_num,
                           header_len, flags_byte,
                           window_size, checksum, urgent_ptr)
        
        # Calcula checksum real (simplificado)
        checksum = Packet.calculate_checksum(header + data)[:2]
        header = header[:16] + checksum + header[18:]
        
        return header + data
    
    @staticmethod
    def parse_segment(segment):
        """Parseia um segmento TCP."""
        if len(segment) < 20:
            return None
        
        header = segment[:20]
        data = segment[20:]
        
        (src_port, dst_port, seq_num, ack_num, header_len,
         flags, window_size, checksum, urgent_ptr) = struct.unpack(TCPSegment.FORMAT, header)
        
        return {
            'src_port': src_port,
            'dst_port': dst_port,
            'seq_num': seq_num,
            'ack_num': ack_num,
            'header_len': header_len,
            'flags': flags,
            'window_size': window_size,
            'checksum': checksum,
            'urgent_ptr': urgent_ptr,
            'data': data
        }

