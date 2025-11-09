import logging
import os
import random
import socket
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fase1.rdt20 import RDT20Sender, RDT20Receiver
from fase1.rdt21 import RDT21Sender, RDT21Receiver
from fase1.rdt30 import RDT30Sender, RDT30Receiver
from collections import defaultdict

from utils.packet import Packet, RDT20Packet, RDT21Packet
from utils.simulator import DirectChannel, UnreliableChannel


def _configure_logging(level=logging.INFO):
    """Configura logging global para os testes."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        force=True,
    )


def _find_free_ports(start_port=5000, step=2):
    """Tenta encontrar duas portas UDP livres (remetente/receptor)."""
    port_sender = start_port
    port_receiver = start_port + 1

    for _ in range(20):
        try:
            sock_a = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock_a.bind(("localhost", port_sender))
            sock_a.close()

            sock_b = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock_b.bind(("localhost", port_receiver))
            sock_b.close()

            return port_sender, port_receiver
        except OSError:
            port_sender += step
            port_receiver += step

    raise RuntimeError("Não foi possível encontrar par de portas livres.")


def _print_header(title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def _format_time(seconds):
    return f"{seconds:.3f} s"


def run_rdt20_perfect():
    _print_header("Teste rdt2.0 - Canal perfeito (10 mensagens, 0% corrupção)")
    _configure_logging(logging.INFO)

    port_sender, port_receiver = _find_free_ports()
    channel = DirectChannel()
    sender = RDT20Sender(port=port_sender, dest_port=port_receiver, channel=channel)
    receiver = RDT20Receiver(port=port_receiver, channel=channel)

    messages = [f"Mensagem {i}" for i in range(10)]
    received = []

    def receiver_loop():
        attempts = 0
        max_attempts = len(messages) * 5
        while len(received) < len(messages) and attempts < max_attempts:
            idx = len(received) + 1
            print(f"[RECEIVER] Aguardando mensagem {idx}/{len(messages)}...")
            msg = receiver.receive(timeout=2)
            attempts += 1
            if msg:
                payload = msg.decode("utf-8")
                received.append(payload)
                print(f"[RECEIVER] Mensagem {len(received)}/{len(messages)} entregue: {payload}")
            else:
                print(f"[RECEIVER] Timeout aguardando mensagem {idx}/{len(messages)}")

    recv_thread = threading.Thread(target=receiver_loop, daemon=True)
    stop_monitor = threading.Event()

    recv_thread.start()
    
    def monitor_retransmissions():
        last_reported = -1
        while not stop_monitor.is_set():
            current = sender.get_retransmissions()
            if current != last_reported:
                print(f"[MONITOR] Retransmissões acumuladas: {current}")
                last_reported = current
            time.sleep(1.0)

    monitor_thread = threading.Thread(target=monitor_retransmissions, daemon=True)
    monitor_thread.start()

    start_time = time.time()
    for idx, msg in enumerate(messages):
        print(f"[SENDER] Enviando mensagem {idx+1}/10: '{msg}'")
        sender.send(msg)
        time.sleep(0.1)

    recv_thread.join(timeout=5)
    elapsed = time.time() - start_time
    stop_monitor.set()
    monitor_thread.join(timeout=2)

    print("\n--- Resumo Canal Perfeito ---")
    print(f"Mensagens esperadas/recebidas: {len(messages)}/{len(received)}")
    print(f"Retransmissões registradas: {sender.get_retransmissions()}")
    print(f"Tempo total: {_format_time(elapsed)}")
    print("Resultado: Todas as mensagens chegaram corretamente." if len(received) == len(messages)
          else "Resultado: Nem todas as mensagens foram entregues.")

    sender.close()
    receiver.close()


def run_rdt20_corruption():
    _print_header(
        "Teste rdt2.0 - Canal com 30% de corrupção (DATA corrompido, ACK íntegro)"
    )
    _configure_logging(logging.DEBUG)
    logging.getLogger("utils.packet").setLevel(logging.INFO)

    class DataCorruptOnlyChannel(UnreliableChannel):
        """Canal que corrompe apenas pacotes DATA (ACK permanece íntegro)."""

        def __init__(self, *args, max_corruptions_per_payload=1, **kwargs):
            super().__init__(*args, **kwargs)
            self.max_corruptions_per_payload = max_corruptions_per_payload
            self._payload_corruptions = {}

        def send(self, packet, dest_socket, dest_addr):
            if random.random() < self.loss_rate:
                print("[SIMULADOR] Pacote perdido pelo canal (rdt2.0)")
                return

            pkt_type, data, _ = RDT20Packet.parse_packet(packet)
            should_corrupt = False

            if pkt_type == Packet.TYPE_DATA:
                key = data
                count = self._payload_corruptions.get(key, 0)
                if count < self.max_corruptions_per_payload and random.random() < self.corrupt_rate:
                    should_corrupt = True
                    self._payload_corruptions[key] = count + 1
                else:
                    self._payload_corruptions[key] = self.max_corruptions_per_payload

            if should_corrupt:
                packet = self._corrupt_packet(packet)
                print(f"[SIMULADOR] Pacote DATA corrompido (tentativa {self._payload_corruptions[data]})")

            delay = random.uniform(*self.delay_range)
            threading.Timer(delay, lambda: dest_socket.sendto(packet, dest_addr)).start()

    port_sender, port_receiver = _find_free_ports(5200)
    channel = DataCorruptOnlyChannel(loss_rate=0.0, corrupt_rate=0.3, delay_range=(0.01, 0.2))
    sender = RDT20Sender(port=port_sender, dest_port=port_receiver, channel=channel)
    receiver = RDT20Receiver(port=port_receiver, channel=channel)

    messages = [f"Msg {i}" for i in range(10)]
    received = []

    def receiver_loop():
        attempts = 0
        max_attempts = len(messages) * 10
        while len(received) < len(messages) and attempts < max_attempts:
            idx = len(received) + 1
            print(f"\n[RECEIVER] Aguardando mensagem {idx}/{len(messages)}...")
            msg = receiver.receive(timeout=10)
            attempts += 1
            if msg:
                payload = msg.decode("utf-8")
                received.append(payload)
                print(f"[RECEIVER] Mensagem {len(received)}/{len(messages)} entregue: '{payload}'")
            else:
                print(f"[RECEIVER] Timeout aguardando mensagem {idx}/{len(messages)} (pode indicar corrupção persistente)")

    recv_thread = threading.Thread(target=receiver_loop, daemon=True)
    recv_thread.start()

    start_time = time.time()
    for idx, msg in enumerate(messages):
        print(f"\n[SENDER] Tentando entregar mensagem {idx+1}/10: '{msg}'")
        sender.send(msg)
        print(f"[SENDER] Retransmissões acumuladas até agora: {sender.get_retransmissions()}")
        time.sleep(0.2)

    recv_thread.join(timeout=40)
    elapsed = time.time() - start_time

    stats = receiver.get_stats()

    print("\n--- Resumo Canal com Corrupção 30% ---")
    print(f"Mensagens esperadas/recebidas: {len(messages)}/{len(received)}")
    print(f"Retransmissões acumuladas (rdt2.0): {sender.get_retransmissions()}")
    print(f"Pacotes corrompidos detectados pelo receptor: {stats['corrupted']}")
    print(f"Tempo total: {_format_time(elapsed)}")
    if len(received) == len(messages):
        print("Resultado: Todas as mensagens chegaram, apesar das corrupções.")
    else:
        print("Resultado: Nem todas as mensagens foram entregues (rdt2.0 pode ficar preso sem timer).")

    sender.close()
    receiver.close()


def _rdt21_overhead_report(messages, received, sender, receiver, elapsed):
    stats_rx = receiver.get_stats()
    payload_bytes = sum(len(m.encode("utf-8")) for m in received)
    data_packets = len(messages) + sender.get_retransmissions()
    data_bytes = data_packets * (len(messages[0]) + 6)  # tipo + seq + checksum
    ack_packets = stats_rx["received"] + stats_rx["duplicates"]
    ack_bytes = ack_packets * 6
    overhead_total = (data_bytes + ack_bytes) - payload_bytes
    overhead_avg = overhead_total / len(messages) if messages else 0

    print(f"Mensagens esperadas/recebidas: {len(messages)}/{len(received)}")
    print(f"Retransmissões: {sender.get_retransmissions()}")
    print(f"Pacotes corrompidos detectados: {stats_rx['corrupted']}")
    print(f"ACKs duplicados enviados: {stats_rx['duplicates']}")
    print(f"Payload entregue: {payload_bytes} bytes")
    print(f"Overhead total (dados + ACKs - payload): {overhead_total} bytes")
    print(f"Overhead médio por mensagem: {overhead_avg:.2f} bytes/mensagem")
    print(f"Tempo total: {_format_time(elapsed)}")

    if len(set(received)) == len(received) == len(messages):
        print("Resultado: Sem duplicação de dados na camada receptora.")
    else:
        print("Resultado: Duplicação detectada! Verificar implementação.")


def run_rdt21_data_corruption():
    _print_header("Teste rdt2.1 - 20% de corrupção somente em DATA")
    _configure_logging(logging.INFO)
    logging.getLogger("utils.packet").setLevel(logging.INFO)

    class RDT21DataCorruptChannel(UnreliableChannel):
        def send(self, packet, dest_socket, dest_addr):
            packet_type, _, _, _ = RDT21Packet.parse_packet(packet)

            if random.random() < self.loss_rate:
                print("[SIMULADOR] Pacote perdido (rdt2.1 DATA)")
                return

            if packet_type == Packet.TYPE_DATA and random.random() < self.corrupt_rate:
                packet = self._corrupt_packet(packet)
                print("[SIMULADOR] Pacote DATA corrompido (rdt2.1)")

            delay = random.uniform(*self.delay_range)
            threading.Timer(delay, lambda: dest_socket.sendto(packet, dest_addr)).start()

    port_sender, port_receiver = _find_free_ports(5400)
    channel = RDT21DataCorruptChannel(
        loss_rate=0.0, corrupt_rate=0.2, delay_range=(0.01, 0.15)
    )
    sender = RDT21Sender(port=port_sender, dest_port=port_receiver, channel=channel)
    receiver = RDT21Receiver(port=port_receiver, channel=channel)

    messages = [f"Msg {i}" for i in range(10)]
    received = []

    def receiver_loop():
        attempts = 0
        max_attempts = len(messages) * 10
        while len(received) < len(messages) and attempts < max_attempts:
            idx = len(received) + 1
            msg = receiver.receive(timeout=5)
            attempts += 1
            if msg:
                payload = msg.decode("utf-8")
                received.append(payload)
                print(f"[RECEIVER] Mensagem {len(received)}/{len(messages)} entregue: '{payload}'")
            else:
                print(f"[RECEIVER] Timeout aguardando mensagem {idx}/{len(messages)}")

    recv_thread = threading.Thread(target=receiver_loop, daemon=True)
    recv_thread.start()

    start_time = time.time()
    for idx, msg in enumerate(messages):
        print(f"[SENDER] Enviando mensagem {idx+1}/10: '{msg}'")
        sender.send(msg)
        time.sleep(0.1)

    recv_thread.join(timeout=20)
    elapsed = time.time() - start_time

    print("\n--- Resumo rdt2.1 (corrupção em DATA) ---")
    _rdt21_overhead_report(messages, received, sender, receiver, elapsed)

    sender.close()
    receiver.close()


def run_rdt21_ack_corruption():
    _print_header("Teste rdt2.1 - 20% de corrupção somente em ACK")
    _configure_logging(logging.INFO)
    logging.getLogger("utils.packet").setLevel(logging.INFO)

    class RDT21AckCorruptChannel(UnreliableChannel):
        def send(self, packet, dest_socket, dest_addr):
            packet_type, _, _, _ = RDT21Packet.parse_packet(packet)

            if random.random() < self.loss_rate:
                print("[SIMULADOR] Pacote perdido (rdt2.1 ACK)")
                return

            if packet_type == Packet.TYPE_ACK and random.random() < self.corrupt_rate:
                packet = self._corrupt_packet(packet)
                print("[SIMULADOR] Pacote ACK corrompido (rdt2.1)")

            delay = random.uniform(*self.delay_range)
            threading.Timer(delay, lambda: dest_socket.sendto(packet, dest_addr)).start()

    port_sender, port_receiver = _find_free_ports(5600)
    channel = RDT21AckCorruptChannel(
        loss_rate=0.0, corrupt_rate=0.2, delay_range=(0.01, 0.15)
    )
    sender = RDT21Sender(port=port_sender, dest_port=port_receiver, channel=channel)
    receiver = RDT21Receiver(port=port_receiver, channel=channel)

    messages = [f"Msg {i}" for i in range(10)]
    received = []

    def receiver_loop():
        attempts = 0
        max_attempts = len(messages) * 10
        while len(received) < len(messages) and attempts < max_attempts:
            idx = len(received) + 1
            msg = receiver.receive(timeout=5)
            attempts += 1
            if msg:
                payload = msg.decode("utf-8")
                received.append(payload)
                print(f"[RECEIVER] Mensagem {len(received)}/{len(messages)} entregue: '{payload}'")
            else:
                print(f"[RECEIVER] Timeout aguardando mensagem {idx}/{len(messages)}")

    recv_thread = threading.Thread(target=receiver_loop, daemon=True)
    recv_thread.start()

    start_time = time.time()
    for idx, msg in enumerate(messages):
        print(f"[SENDER] Enviando mensagem {idx+1}/10: '{msg}'")
        sender.send(msg)
        time.sleep(0.1)

    recv_thread.join(timeout=20)
    elapsed = time.time() - start_time

    print("\n--- Resumo rdt2.1 (corrupção em ACK) ---")
    _rdt21_overhead_report(messages, received, sender, receiver, elapsed)

    sender.close()
    receiver.close()


class RDT30SelectiveLossChannel(UnreliableChannel):
    """Canal que permite configurar perdas e corrupções com limites para DATA e ACK."""

    def __init__(
        self,
        data_loss=0.0,
        ack_loss=0.0,
        corrupt_rate=0.0,
        delay_range=(0.01, 0.1),
        max_corruptions_per_data=1,
        max_corruptions_per_ack=1,
    ):
        super().__init__(loss_rate=0.0, corrupt_rate=corrupt_rate, delay_range=delay_range)
        self.data_loss = data_loss
        self.ack_loss = ack_loss
        self.max_corruptions_per_data = max_corruptions_per_data
        self.max_corruptions_per_ack = max_corruptions_per_ack
        self._corruption_tracker = defaultdict(int)

    def send(self, packet, dest_socket, dest_addr):
        packet_type, seq_num, data, _ = RDT21Packet.parse_packet(packet)
        loss_rate = self.data_loss if packet_type == Packet.TYPE_DATA else self.ack_loss if packet_type == Packet.TYPE_ACK else 0.0

        if random.random() < loss_rate:
            tipo = "DATA" if packet_type == Packet.TYPE_DATA else "ACK"
            print(f"[SIMULADOR] Pacote {tipo} perdido (rdt3.0)")
            return

        should_corrupt = False
        if random.random() < self.corrupt_rate:
            if packet_type == Packet.TYPE_DATA:
                key = (packet_type, seq_num, data)
                limit = self.max_corruptions_per_data
            elif packet_type == Packet.TYPE_ACK:
                key = (packet_type, seq_num)
                limit = self.max_corruptions_per_ack
            else:
                key = (packet_type, seq_num)
                limit = None

            if limit is None or self._corruption_tracker[key] < limit:
                should_corrupt = True
                self._corruption_tracker[key] += 1

        if should_corrupt:
            packet = self._corrupt_packet(packet)
            tipo = "DATA" if packet_type == Packet.TYPE_DATA else "ACK"
            print(f"[SIMULADOR] Pacote {tipo} corrompido (rdt3.0) - tentativa {self._corruption_tracker[key]}")

        delay = random.uniform(*self.delay_range)
        threading.Timer(delay, lambda: dest_socket.sendto(packet, dest_addr)).start()


def _execute_rdt30_test(title, channel_factory, start_port):
    _print_header(title)
    _configure_logging(logging.INFO)
    logging.getLogger("utils.packet").setLevel(logging.INFO)

    port_sender, port_receiver = _find_free_ports(start_port)
    channel = channel_factory()
    sender = RDT30Sender(port=port_sender, dest_port=port_receiver, channel=channel)
    receiver = RDT30Receiver(port=port_receiver, channel=channel)

    messages = [f"Msg {i}" for i in range(10)]
    received = []

    def receiver_loop():
        attempts = 0
        max_attempts = len(messages) * 12
        while len(received) < len(messages) and attempts < max_attempts:
            idx = len(received) + 1
            msg = receiver.receive(timeout=10)
            attempts += 1
            if msg:
                payload = msg.decode("utf-8")
                received.append(payload)
                print(f"[RECEIVER] Mensagem {len(received)}/{len(messages)} entregue: '{payload}'")
            else:
                print(f"[RECEIVER] Timeout aguardando mensagem {idx}/{len(messages)}")

    recv_thread = threading.Thread(target=receiver_loop, daemon=True)
    recv_thread.start()

    start_time = time.time()
    for idx, msg in enumerate(messages):
        print(f"[SENDER] Enviando mensagem {idx+1}/10: '{msg}'")
        sender.send(msg)
        time.sleep(0.15)

    recv_thread.join(timeout=60)
    elapsed = time.time() - start_time

    stats_tx = sender.get_stats()
    stats_rx = receiver.get_stats()
    payload_bytes = sum(len(m.encode("utf-8")) for m in received)
    throughput = (payload_bytes * 8) / elapsed if elapsed > 0 else 0

    total_transmissoes = len(messages) + stats_tx['retransmissions']
    retransmission_rate = (stats_tx['retransmissions'] / total_transmissoes) if total_transmissoes > 0 else 0.0

    print("\n--- Resumo rdt3.0 ---")
    print(f"Mensagens esperadas/recebidas: {len(messages)}/{len(received)}")
    print(f"Retransmissões (sender): {stats_tx['retransmissions']}")
    print(f"Taxa de retransmissão: {retransmission_rate*100:.2f}% ({stats_tx['retransmissions']}/{total_transmissoes} transmissões totais)")
    print(f"Pacotes corrompidos detectados no receptor: {stats_rx['corrupted']}")
    print(f"Tempo total: {_format_time(elapsed)}")
    print(f"Throughput efetivo (payload): {throughput/1_000_000:.4f} Mbps")
    print(f"Throughput total enviado (stats sender): {stats_tx['throughput_mbps']:.4f} Mbps")

    if len(received) == len(messages):
        print("Resultado: Todas as mensagens foram entregues corretamente.")
    else:
        print("Resultado: Perdas impediram a entrega completa.")

    sender.close()
    receiver.close()


def run_rdt30_data_loss():
    def channel_factory():
        return RDT30SelectiveLossChannel(
            data_loss=0.15,
            ack_loss=0.0,
            corrupt_rate=0.0,
            delay_range=(0.01, 0.15),
        )

    _execute_rdt30_test("Teste rdt3.0 - Perda de 15% apenas em DATA", channel_factory, start_port=6200)


def run_rdt30_ack_loss():
    def channel_factory():
        return RDT30SelectiveLossChannel(
            data_loss=0.0,
            ack_loss=0.15,
            corrupt_rate=0.0,
            delay_range=(0.01, 0.15),
        )

    _execute_rdt30_test("Teste rdt3.0 - Perda de 15% apenas em ACK", channel_factory, start_port=6400)


def run_rdt30_variable_delay():
    def channel_factory():
        return RDT30SelectiveLossChannel(
            data_loss=0.0,
            ack_loss=0.0,
            corrupt_rate=0.0,
            delay_range=(0.05, 0.5),
        )

    _execute_rdt30_test("Teste rdt3.0 - Atraso variável (50-500ms) sem perdas", channel_factory, start_port=6600)


def menu_rdt20():
    while True:
        print("\n--- Menu RDT 2.0 ---")
        print("1 - Canal perfeito (10 mensagens)")
        print("2 - Canal com 30% de corrupção (logs detalhados)")
        print("0 - Voltar")
        choice = input("Escolha uma opção: ").strip()

        if choice == "1":
            run_rdt20_perfect()
        elif choice == "2":
            run_rdt20_corruption()
        elif choice == "0":
            break
        else:
            print("Opção inválida. Tente novamente.")


def menu_rdt21():
    while True:
        print("\n--- Menu RDT 2.1 ---")
        print("1 - Corrupção de 20% apenas em DATA")
        print("2 - Corrupção de 20% apenas em ACK")
        print("0 - Voltar")
        choice = input("Escolha uma opção: ").strip()

        if choice == "1":
            run_rdt21_data_corruption()
        elif choice == "2":
            run_rdt21_ack_corruption()
        elif choice == "0":
            break
        else:
            print("Opção inválida. Tente novamente.")


def menu_rdt30():
    while True:
        print("\n--- Menu RDT 3.0 ---")
        print("1 - Perda de 15% apenas em DATA")
        print("2 - Perda de 15% apenas em ACK")
        print("3 - Atraso variável (50-500ms)")
        print("0 - Voltar")
        choice = input("Escolha uma opção: ").strip()

        if choice == "1":
            run_rdt30_data_loss()
        elif choice == "2":
            run_rdt30_ack_loss()
        elif choice == "3":
            run_rdt30_variable_delay()
        elif choice == "0":
            break
        else:
            print("Opção inválida. Tente novamente.")


def main_menu():
    print("Executando testes da Fase 1 (Selecione o protocolo desejado)")
    while True:
        print("\n=== Menu Principal ===")
        print("1 - Testes RDT 2.0")
        print("2 - Testes RDT 2.1")
        print("3 - Testes RDT 3.0")
        print("0 - Sair")
        choice = input("Escolha uma opção: ").strip()

        if choice == "1":
            menu_rdt20()
        elif choice == "2":
            menu_rdt21()
        elif choice == "3":
            menu_rdt30()
        elif choice == "0":
            print("Encerrando testes da Fase 1.")
            break
        else:
            print("Opção inválida. Tente novamente.")


if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        print("\nExecução interrompida pelo usuário.")

