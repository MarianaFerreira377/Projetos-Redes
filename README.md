# Projeto Redes - Transferência Confiável de Dados e TCP sobre UDP

Implementação progressiva de protocolos de transferência confiável de dados sobre UDP, seguindo a evolução apresentada no Capítulo 3 do livro "Computer Networking: A Top-Down Approach" (Kurose & Ross, 8ª edição).

## Estrutura do Projeto

```
projeto_redes/
├── fase1/              # Protocolos RDT (rdt2.0, rdt2.1, rdt3.0)
│   ├── rdt20.py
│   ├── rdt21.py
│   └── rdt30.py
├── fase2/              # Pipelining (Go-Back-N)
│   └── gbn.py
├── fase3/              # TCP Simplificado
│   ├── tcp_socket.py
│   ├── tcp_server.py
│   └── tcp_client.py
├── testes/             # Testes automatizados
│   ├── test_fase1.py
│   ├── test_fase2.py
│   └── test_fase3.py
├── utils/              # Utilitários
│   ├── packet.py       # Estruturas de pacotes
│   ├── simulator.py    # Simulador de canal não confiável
│   └── logger.py      # Sistema de logging
└── README.md
```

## Requisitos

- Python 3.8 ou superior
- Bibliotecas padrão do Python (socket, threading, struct, hashlib, time, random)

## Instalação

Não há dependências externas. O projeto usa apenas bibliotecas padrão do Python.

```bash
cd /home/mariana-assis/Documentos/ProjetoRedes
```

## Execução

### Fase 1: Protocolos RDT

#### Teste rdt2.0
```bash
python testes/test_fase1.py
```

#### Teste individual rdt2.0
```python
from fase1.rdt20 import RDT20Sender, RDT20Receiver
from utils.simulator import DirectChannel

channel = DirectChannel()
sender = RDT20Sender(port=5000, dest_port=5001, channel=channel)
receiver = RDT20Receiver(port=5001, channel=channel)

# Em terminal separado ou thread
receiver.receive()

# Enviar mensagem
sender.send("Mensagem de teste")
```

#### Teste rdt2.1
```python
from fase1.rdt21 import RDT21Sender, RDT21Receiver
from utils.simulator import UnreliableChannel

channel = UnreliableChannel(loss_rate=0.0, corrupt_rate=0.2)
sender = RDT21Sender(port=5000, dest_port=5001, channel=channel)
receiver = RDT21Receiver(port=5001, channel=channel)
```

#### Teste rdt3.0
```python
from fase1.rdt30 import RDT30Sender, RDT30Receiver
from utils.simulator import UnreliableChannel

channel = UnreliableChannel(loss_rate=0.15, corrupt_rate=0.1)
sender = RDT30Sender(port=5000, dest_port=5001, channel=channel)
receiver = RDT30Receiver(port=5001, channel=channel)
```

### Fase 2: Go-Back-N

#### Executar testes
```bash
python testes/test_fase2.py
```

#### Exemplo de uso
```python
from fase2.gbn import GBNSender, GBNReceiver
from utils.simulator import UnreliableChannel

channel = UnreliableChannel(loss_rate=0.1, corrupt_rate=0.05)
sender = GBNSender(port=6000, dest_port=6001, channel=channel, window_size=5)
receiver = GBNReceiver(port=6001, channel=channel)

# Enviar múltiplos pacotes
for i in range(10):
    sender.send(f"Mensagem {i}".encode())
    time.sleep(0.1)

sender.wait_for_all_acks()
```

### Fase 3: TCP Simplificado

#### Executar servidor e cliente

**Terminal 1 - Servidor:**
```bash
python fase3/tcp_server.py
```

**Terminal 2 - Cliente:**
```bash
python fase3/tcp_client.py
```

#### Executar testes
```bash
python testes/test_fase3.py
```

#### Exemplo de uso programático
```python
from fase3.tcp_socket import SimpleTCPSocket

# Servidor
server = SimpleTCPSocket(8000)
server.listen()
conn = server.accept()

# Cliente
client = SimpleTCPSocket(9000)
client.connect(('localhost', 8000))

# Transferir dados
data = b'x' * 10240
client.send(data)
received = conn.recv(10240)

# Encerrar
client.close()
conn.close()
```

## Testes Automatizados

Todos os testes podem ser executados de uma vez:

```bash
# Teste Fase 1
python testes/test_fase1.py

# Teste Fase 2
python testes/test_fase2.py

# Teste Fase 3
python testes/test_fase3.py
```

## Simulador de Canal Não Confiável

O simulador permite configurar:
- **loss_rate**: probabilidade de perda de pacotes (0.0 a 1.0)
- **corrupt_rate**: probabilidade de corrupção (0.0 a 1.0)
- **delay_range**: tupla (min_delay, max_delay) em segundos

Exemplo:
```python
from utils.simulator import UnreliableChannel

# Canal com 10% de perda, 20% de corrupção, delay de 50-500ms
channel = UnreliableChannel(
    loss_rate=0.1,
    corrupt_rate=0.2,
    delay_range=(0.05, 0.5)
)
```

## Características Implementadas

### Fase 1: Protocolos RDT
- ✅ rdt2.0: ACK/NAK com checksum
- ✅ rdt2.1: Números de sequência alternantes (0/1)
- ✅ rdt3.0: Timer e tratamento de perda de pacotes

### Fase 2: Go-Back-N
- ✅ Janela deslizante de tamanho configurável
- ✅ ACKs cumulativos
- ✅ Retransmissão em caso de timeout
- ✅ Tratamento de pacotes fora de ordem

### Fase 3: TCP Simplificado
- ✅ Three-way handshake (SYN, SYN-ACK, ACK)
- ✅ Transferência confiável de dados
- ✅ Números de sequência baseados em bytes
- ✅ ACKs cumulativos
- ✅ Controle de fluxo (janela de recepção)
- ✅ Retransmissão com timeout adaptativo (estimativa de RTT)
- ✅ Four-way handshake de encerramento (FIN, ACK, FIN, ACK)
- ✅ Buffers de envio e recepção

## Logging

O sistema usa logging do Python para debug. Os logs mostram:
- Pacotes enviados/recebidos
- ACKs e NAKs
- Retransmissões
- Timeouts
- Estados da conexão (para TCP)

## Limitações

Esta é uma implementação simplificada e não inclui:
- Controle de congestionamento
- Timestamps TCP
- Opções TCP
- Tratamento completo de pacotes fora de ordem (em algumas fases)
- Bufferização sofisticada de pacotes fora de ordem (no TCP simplificado)

## Referências

- KUROSE, J. F.; ROSS, K. W. Computer Networking: A Top-Down Approach. 8th ed. Pearson, 2021. Chapter 3.
- RFC 793: Transmission Control Protocol

## Autores

Projeto desenvolvido para a disciplina de Redes de Computadores.

## Licença

Este projeto é para fins educacionais.

