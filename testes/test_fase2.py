"""
Testes interativos para Fase 2 - Go-Back-N (GBN).
"""
import sys
import os
import time
import math
import socket
import logging
import threading

import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fase1.rdt30 import RDT30Sender, RDT30Receiver
from fase2.gbn import GBNSender, GBNReceiver
from utils.simulator import UnreliableChannel, DirectChannel, GBNBoundedLossChannel



def _configure_logging(level=logging.INFO):
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def _set_protocol_logging(level):
    """
    Ajusta o nível de log dos principais componentes para evitar spam em testes longos.
    """
    for logger_name in (
        "RDT30Sender",
        "RDT30Receiver",
        "GBNSender",
        "GBNReceiver",
        "utils.packet",
        "utils.simulator",
    ):
        logger = logging.getLogger(logger_name)
        logger.setLevel(level)
        for handler in logger.handlers:
            handler.setLevel(level)


def _print_header(title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def _find_free_ports(start_port=6500):
    """Encontra duas portas UDP livres a partir de um valor base."""
    port = start_port
    while port < 65535:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s1, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s2:
            try:
                s1.bind(("localhost", port))
                s2.bind(("localhost", port + 1))
                return port, port + 1
            except OSError:
                port += 2
    raise RuntimeError("Não foi possível encontrar portas UDP livres.")


def _calc_utilization(payload_bytes, chunk_bytes, retransmissions):
    """Calcula utilização do canal considerando retransmissões."""
    total_sent = payload_bytes + retransmissions * chunk_bytes
    if total_sent == 0:
        return 0.0
    return payload_bytes / total_sent


def _calc_retransmission_rate(total_packets, retransmissions):
    if total_packets == 0:
        return 0.0
    return retransmissions / total_packets


def _plot_window_throughput(resultados, filename="gbn_throughput.png"):
    """
    Gera gráfico Throughput x Tamanho da Janela e salva como PNG.
    """
    if not resultados:
        logging.warning("Sem dados para plotar throughput x janela.")
        return None

    resultados_ordenados = sorted(resultados, key=lambda item: item["janela"])
    janelas = [item["janela"] for item in resultados_ordenados]
    thputs = [item["throughput_mbps"] for item in resultados_ordenados]

    output_dir = os.path.join(os.path.dirname(__file__), "plots")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, filename)

    plt.figure(figsize=(8, 5))
    plt.plot(janelas, thputs, marker="o", linewidth=2, color="#1f77b4")
    plt.title("Throughput x Tamanho da Janela (GBN)")
    plt.xlabel("Tamanho da Janela (N)")
    plt.ylabel("Throughput (Mbps)")
    plt.grid(True, linestyle="--", alpha=0.4)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()

    print(f"Gráfico gerado em: {output_path}")
    return output_path


# ---------------------------------------------------------------------------
# Testes / Cenários interativos
# ---------------------------------------------------------------------------

def _run_stop_and_wait_1mb():
    total_bytes = 1 * 1024 * 1024
    chunk_size = 1024 * 5  # 5 KB por pacote
    total_chunks = math.ceil(total_bytes / chunk_size)

    ports = _find_free_ports(7000)
    channel = DirectChannel()
    sender = RDT30Sender(port=ports[0], dest_port=ports[1], channel=channel)
    receiver = RDT30Receiver(port=ports[1], channel=channel)

    received = 0

    def _recv_loop():
        nonlocal received
        while received < total_chunks:
            data = receiver.receive(timeout=5)
            if data:
                received += 1

    thread = threading.Thread(target=_recv_loop, daemon=True)
    thread.start()

    start = time.time()
    sent_payload = 0
    for _ in range(total_chunks):
        remaining = total_bytes - sent_payload
        current_size = chunk_size if remaining >= chunk_size else remaining
        payload = b'x' * current_size
        sender.send(payload)
        sent_payload += current_size
    end = time.time()

    thread.join(timeout=30)
    stats = sender.get_stats()
    retrans = sender.get_retransmissions()
    total_packets = total_chunks + retrans
    util = _calc_utilization(total_bytes, chunk_size, retrans)
    throughput = (total_bytes * 8 / (end - start)) / 1_000_000 if end > start else 0.0

    sender.close()
    receiver.close()

    return {
        "protocol": "rdt3.0 (Stop-and-Wait)",
        "tempo": end - start,
        "throughput": throughput,
        "retransmissoes": retrans,
        "taxa_retrans": _calc_retransmission_rate(total_packets, retrans) * 100,
        "utilizacao": util * 100,
    }


def _run_gbn_1mb(window_size=5):
    total_bytes = 1 * 1024 * 1024
    chunk_size = 1024 * window_size  # Alinha tamanho do bloco à janela padrão
    total_chunks = math.ceil(total_bytes / chunk_size)

    ports = _find_free_ports(7200 + window_size)
    channel = DirectChannel()
    sender = GBNSender(port=ports[0], dest_port=ports[1], channel=channel, window_size=window_size)
    receiver = GBNReceiver(port=ports[1], channel=channel)

    received = 0

    def _recv_loop():
        nonlocal received
        while received < total_chunks:
            data = receiver.receive(timeout=5)
            if data:
                received += 1

    thread = threading.Thread(target=_recv_loop, daemon=True)
    thread.start()

    start = time.time()
    sent_payload = 0
    for _ in range(total_chunks):
        remaining = total_bytes - sent_payload
        current_size = chunk_size if remaining >= chunk_size else remaining
        payload = b'x' * current_size
        while not sender.send(payload):
            time.sleep(0.001)
        sent_payload += current_size
        time.sleep(0.02)
    sender.wait_for_all_acks(timeout=120)
    end = time.time()

    thread.join(timeout=30)
    stats = sender.get_stats()
    retrans = sender.get_retransmissions()
    total_packets = total_chunks + retrans
    util = _calc_utilization(total_bytes, chunk_size, retrans)
    throughput = (total_bytes * 8 / (end - start)) / 1_000_000 if end > start else 0.0

    sender.close()
    receiver.close()

    return {
        "protocol": f"GBN (janela={window_size})",
        "tempo": end - start,
        "throughput": throughput,
        "retransmissoes": retrans,
        "taxa_retrans": _calc_retransmission_rate(total_packets, retrans) * 100,
        "utilizacao": util * 100,
    }


def run_gbn_efficiency():
    """Executa o cenário completo de eficiência (rdt3.0 x GBN)."""
    _print_header("Fase 2 - Comparação: Stop-and-Wait vs GBN")
    _configure_logging(logging.INFO)
    _set_protocol_logging(logging.INFO)
    result_rdt = _run_stop_and_wait_1mb()
    result_gbn = _run_gbn_1mb(window_size=5)
    speedup = (
        result_rdt["tempo"] / result_gbn["tempo"]
        if result_gbn["tempo"] > 0
        else float("inf")
    )
    print("\n--- Stop-and-Wait ---")
    print(
        f"Tempo: {result_rdt['tempo']:.3f} s | "
        f"Throughput: {result_rdt['throughput']:.3f} Mbps | "
        f"Retrans.: {result_rdt['retransmissoes']} "
        f"({result_rdt['taxa_retrans']:.2f}%) | "
        f"Utilização: {result_rdt['utilizacao']:.2f}%"
    )
    print("\n--- Go-Back-N ---")
    print(
        f"Tempo: {result_gbn['tempo']:.3f} s | "
        f"Throughput: {result_gbn['throughput']:.3f} Mbps | "
        f"Retrans.: {result_gbn['retransmissoes']} "
        f"({result_gbn['taxa_retrans']:.2f}%) | "
        f"Utilização: {result_gbn['utilizacao']:.2f}%"
    )
    print(f"\nAceleração estimada (GBN vs rdt3.0): {speedup:.2f}x")

    print("\nResumo comparativo:")
    print("=" * 70)
    print(
        f"{'Protocolo':<25}{'Tempo (s)':>12}{'Throughput (Mbps)':>20}"
        f"{'Retransm.':>12}{'Taxa Retrans.':>16}"
    )
    print("-" * 70)
    print(
        f"{result_rdt['protocol']:<25}"
        f"{result_rdt['tempo']:>12.3f}"
        f"{result_rdt['throughput']:>20.3f}"
        f"{result_rdt['retransmissoes']:>12}"
        f"{result_rdt['taxa_retrans']:>15.2f}%"
    )
    print(
        f"{result_gbn['protocol']:<25}"
        f"{result_gbn['tempo']:>12.3f}"
        f"{result_gbn['throughput']:>20.3f}"
        f"{result_gbn['retransmissoes']:>12}"
        f"{result_gbn['taxa_retrans']:>15.2f}%"
    )
    print("=" * 70)


def run_gbn_loss():
    """
    Teste com canal apresentando 10% de perdas (somente perda, sem corrupção).
    Verifica entrega completa e contabiliza retransmissões.
    """
    _print_header("Fase 2 - Teste com Perdas (10%)")
    _configure_logging(logging.WARNING)

    num_msgs = 20
    payload = b'Pacote_GBN' * 64  # ~640 bytes
    chunk_size = len(payload)

    channel = GBNBoundedLossChannel(
        loss_rate=0.1,
        corrupt_rate=0.0,
        delay_range=(0.01, 0.15),
    )
    port_sender, port_receiver = _find_free_ports(7600)

    sender = GBNSender(port=port_sender, dest_port=port_receiver, channel=channel, window_size=8, timeout=1.0)
    receiver = GBNReceiver(port=port_receiver, channel=channel)

    received = []

    def _recv_loop():
        deadline = time.time() + 180  # até 3 minutos escutando
        while len(received) < num_msgs and time.time() < deadline:
            data = receiver.receive(timeout=5)
            if data:
                received.append(data)

    recv_thread = threading.Thread(target=_recv_loop, daemon=True)
    recv_thread.start()

    for _ in range(num_msgs):
        while not sender.send(payload):
            time.sleep(0.002)

    sender.wait_for_all_acks(timeout=120)
    recv_thread.join(timeout=60)

    retrans = sender.get_retransmissions()
    total_packets = num_msgs + retrans
    util = _calc_utilization(num_msgs * chunk_size, chunk_size, retrans)
    stats = sender.get_stats()
    throughput = stats['throughput_mbps']

    print("\n--- Resumo (Perda 10%) ---")
    print(f"Mensagens esperadas/recebidas: {num_msgs}/{len(received)}")
    print(f"Retransmissões: {retrans}")
    print(f"Taxa de retransmissão: {_calc_retransmission_rate(total_packets, retrans)*100:.2f}%")
    print(f"Utilização estimada do canal: {util*100:.2f}%")
    print(f"Throughput observado: {throughput:.4f} Mbps")
    print("Resultado:", "todas as mensagens chegaram." if len(received) == num_msgs else "mensagens faltantes!")

    sender.close()
    receiver.close()


def run_gbn_window_analysis(window_sizes=None, generate_plot=True):
    """
    Executa a análise completa para N = 1, 5, 10 e 20 (canal perfeito).
    Gera valores de tempo, throughput, retransmissões e utilização.
    """
    _print_header("Fase 2 - Análise por Tamanho de Janela")
    _configure_logging(logging.INFO)
    _set_protocol_logging(logging.INFO)

    if window_sizes is None:
        window_sizes = [1, 5, 10, 20]
    else:
        window_sizes = list(dict.fromkeys(window_sizes))
    num_msgs = 100
    payload = b'GBN_WINDOW' * 64  # ~640 bytes
    chunk_size = len(payload)

    resultados = []

    for idx, N in enumerate(window_sizes, start=1):
        print(f"\n[Análise] ({idx}/{len(window_sizes)}) Executando GBN com janela N={N}...")
        port_sender, port_receiver = _find_free_ports(8000 + N * 10)
        channel = DirectChannel()
        sender = GBNSender(
            port=port_sender,
            dest_port=port_receiver,
            channel=channel,
            window_size=N,
            timeout=1.0,
        )
        receiver = GBNReceiver(port=port_receiver, channel=channel)

        recebidos = 0
        stop_event = threading.Event()

        def _recv_loop():
            nonlocal recebidos
            while True:
                data = receiver.receive(timeout=5)
                if data:
                    recebidos += 1
                    if recebidos >= num_msgs:
                        break
                else:
                    if stop_event.is_set():
                        break

        recv_thread = threading.Thread(target=_recv_loop, daemon=True)
        recv_thread.start()

        start = time.time()
        for _ in range(num_msgs):
            while not sender.send(payload):
                time.sleep(0.001)
        sender.wait_for_all_acks(timeout=120)
        stop_event.set()
        end = time.time()

        recv_thread.join(timeout=30)
        retrans = sender.get_retransmissions()
        total_packets = num_msgs + retrans
        util = _calc_utilization(num_msgs * chunk_size, chunk_size, retrans)
        stats = sender.get_stats()
        throughput = stats['throughput_mbps']

        resultados.append(
            {
                "janela": N,
                "tempo": end - start,
                "throughput_mbps": throughput,
                "retransmissoes": retrans,
                "taxa_retrans": _calc_retransmission_rate(total_packets, retrans) * 100,
                "utilizacao": util * 100,
            }
        )

        sender.close()
        receiver.close()
        time.sleep(0.5)

    print("\n--- Resumo (Throughput x Janela) ---")
    for item in resultados:
        print(
            f"N={item['janela']:>2} | tempo={item['tempo']:.3f}s | "
            f"throughput={item['throughput_mbps']:.4f} Mbps | "
            f"retr={item['retransmissoes']} ({item['taxa_retrans']:.2f}%) | "
            f"utilização={item['utilizacao']:.2f}%"
        )

    print("\nDica: utilize os dados acima para gerar o gráfico Throughput x N no relatório.")

    if generate_plot:
        _plot_window_throughput(resultados)

# ---------------------------------------------------------------------------
# Submenus
# ---------------------------------------------------------------------------

def menu_efficiency():
    while True:
        print("\n--- Teste de Eficiência (1 MB) ---")
        print("1 - Transferir 1MB de dados (GBN)")
        print("2 - Comparar tempo com rdt3.0 (stop-and-wait)")
        print("3 - Calcular utilização do canal (GBN)")
        print("0 - Voltar")
        choice = input("Escolha uma opção: ").strip()

        if choice == "1":
            _print_header("Fase 2 - GBN (janela=5) - 1 MB")
            _configure_logging(logging.INFO)
            _set_protocol_logging(logging.INFO)
            result = _run_gbn_1mb(window_size=5)
            print(
                f"Protocolo: {result['protocol']}\n"
                f"Tempo total: {result['tempo']:.3f} s\n"
                f"Throughput payload: {result['throughput']:.3f} Mbps\n"
                f"Retransmissões: {result['retransmissoes']} "
                f"(taxa: {result['taxa_retrans']:.2f}%)\n"
                f"Utilização do canal: {result['utilizacao']:.2f}%"
            )
        elif choice == "2":
            _print_header("Fase 2 - Comparação: Stop-and-Wait vs GBN")
            _configure_logging(logging.INFO)
            _set_protocol_logging(logging.INFO)

            # Executa rdt3.0 (stop-and-wait) em canal direto
            result_rdt = _run_stop_and_wait_1mb()

            # Executa GBN com janela 5 em canal direto
            result_gbn = _run_gbn_1mb(window_size=5)

            speedup = (
                result_rdt["tempo"] / result_gbn["tempo"]
                if result_gbn["tempo"] > 0
                else float("inf")
            )

            print("\n--- Stop-and-Wait (rdt3.0) ---")
            print(
                f"Tempo: {result_rdt['tempo']:.3f} s | "
                f"Throughput: {result_rdt['throughput']:.3f} Mbps | "
                f"Retrans.: {result_rdt['retransmissoes']} "
                f"({result_rdt['taxa_retrans']:.2f}%) | "
                f"Utilização: {result_rdt['utilizacao']:.2f}%"
            )

            print("\n--- Go-Back-N ---")
            print(
                f"Tempo: {result_gbn['tempo']:.3f} s | "
                f"Throughput: {result_gbn['throughput']:.3f} Mbps | "
                f"Retrans.: {result_gbn['retransmissoes']} "
                f"({result_gbn['taxa_retrans']:.2f}%) | "
                f"Utilização: {result_gbn['utilizacao']:.2f}%"
            )

            print(f"\nAceleração estimada (GBN vs rdt3.0): {speedup:.2f}x")
        elif choice == "3":
            _print_header("Fase 2 - Utilização do Canal (GBN)")
            _configure_logging(logging.INFO)
            _set_protocol_logging(logging.INFO)
            result = _run_gbn_1mb(window_size=5)
            print(
                f"Protocolo: {result['protocol']}\n"
                f"Utilização estimada do canal: {result['utilizacao']:.2f}%\n"
                f"Retransmissões: {result['retransmissoes']} "
                f"(taxa: {result['taxa_retrans']:.2f}%)\n"
                f"Throughput payload: {result['throughput']:.3f} Mbps"
            )
        elif choice == "0":
            break
        else:
            print("Opção inválida. Tente novamente.")


def menu_loss():
    print("\n--- Teste com Perdas ---")
    print("- Taxa de perda de 10%")
    print("- Verificar se todas as mensagens chegam")
    print("- Contar retransmissões")
    _configure_logging(logging.INFO)
    _set_protocol_logging(logging.INFO)
    run_gbn_loss()


def menu_window_analysis():
    print("\n--- Análise Tamanho de Janela ---")
    print("- Variar tamanho da janela (N = 1, 5, 10, 20)")
    print("- Plotar gráfico: Throughput x Tamanho da Janela")
    run_gbn_window_analysis(generate_plot=True)


# ---------------------------------------------------------------------------
# Menu interativo
# ---------------------------------------------------------------------------

def menu_fase2():
    while True:
        print("\n--- Menu Fase 2 (Go-Back-N) ---")
        print("1 - Teste de Eficiência")

        print("2 - Teste com Perdas")

        print("3 - Análise de Desempenho")

        print("0 - Voltar/Sair")
        choice = input("Escolha uma opção: ").strip()

        if choice == "1":
            menu_efficiency()
        elif choice == "2":
            menu_loss()
        elif choice == "3":
            menu_window_analysis()
        elif choice == "0":
            break
        else:
            print("Opção inválida. Tente novamente.")


if __name__ == "__main__":
    menu_fase2()

