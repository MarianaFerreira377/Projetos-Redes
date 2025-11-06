"""
Script para executar todos os testes do projeto.
"""
import sys
import os

# Adiciona o diretório raiz ao path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    """Executa todos os testes."""
    print("=" * 60)
    print("EXECUTANDO TODOS OS TESTES DO PROJETO")
    print("=" * 60)
    
    tests = [
        ("Fase 1 - Protocolos RDT", "testes/test_fase1.py"),
        ("Fase 2 - Go-Back-N", "testes/test_fase2.py"),
        ("Fase 3 - TCP Simplificado", "testes/test_fase3.py"),
    ]
    
    results = []
    
    for test_name, test_file in tests:
        print(f"\n{'=' * 60}")
        print(f"Executando: {test_name}")
        print(f"{'=' * 60}")
        
        try:
            # Executa o arquivo de teste
            with open(test_file, 'r') as f:
                code = compile(f.read(), test_file, 'exec')
                exec(code, {'__name__': '__main__'})
            
            results.append((test_name, True, None))
            print(f"\n✓ {test_name} - PASSOU")
            
        except AssertionError as e:
            results.append((test_name, False, str(e)))
            print(f"\n✗ {test_name} - FALHOU: {e}")
        except Exception as e:
            results.append((test_name, False, str(e)))
            print(f"\n✗ {test_name} - ERRO: {e}")
            import traceback
            traceback.print_exc()
    
    # Resumo
    print(f"\n{'=' * 60}")
    print("RESUMO DOS TESTES")
    print(f"{'=' * 60}")
    
    passed = sum(1 for _, success, _ in results if success)
    total = len(results)
    
    for test_name, success, error in results:
        status = "✓ PASSOU" if success else f"✗ FALHOU ({error})"
        print(f"  {test_name}: {status}")
    
    print(f"\nTotal: {passed}/{total} testes passaram")
    
    if passed == total:
        print("\n🎉 Todos os testes passaram!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} teste(s) falharam")
        return 1


if __name__ == '__main__':
    sys.exit(main())

