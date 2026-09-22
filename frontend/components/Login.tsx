import React, { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '@/hooks/use-auth'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { AbrLogo } from '@/components/AbrLogo'
import { Loader2, ArrowRight, Lock, AlertCircle, ShieldCheck, Sparkles } from 'lucide-react'

export default function Login() {
  const [email, setEmail] = useState('pietra.leite@grupoabr.com.br')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)

  const { signIn } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const from = (location.state as any)?.from?.pathname || '/cockpit'

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setErrorMsg(null)

    if (!email || !password) {
      setErrorMsg('Preencha e-mail e senha para continuar.')
      return
    }

    setLoading(true)
    try {
      const { error } = await signIn(email.trim(), password)
      if (error) {
        setErrorMsg('Credenciais inválidas. Verifique seu e-mail e senha.')
      } else {
        navigate(from, { replace: true })
      }
    } catch (err: any) {
      setErrorMsg('Falha ao autenticar. Tente novamente.')
    } finally {
      setLoading(false)
    }
  }

  const setDemoUser = (userEmail: string) => {
    setEmail(userEmail)
    setPassword('')
    setErrorMsg(null)
  }

  return (
    <div className="relative min-h-screen w-full flex items-center justify-center p-4 bg-gradient-to-br from-[#142758] via-[#253575] to-[#142758] text-white overflow-hidden">
      {/* CURVA LARANJA COMO GRAFISMO PROPRIETÁRIO (Manual: elemento de movimento, continuidade e direção) */}
      <div className="absolute inset-x-0 -bottom-10 pointer-events-none opacity-90">
        <svg
          viewBox="0 0 1440 280"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          preserveAspectRatio="none"
          className="w-full h-44 md:h-64"
        >
          <path
            d="M-20,180 Q360,20 820,160 T1480,90 L1480,300 L-20,300 Z"
            fill="#F18800"
            fillOpacity="0.22"
          />
          <path
            d="M-20,210 Q380,80 860,190 T1480,120"
            stroke="#F18800"
            strokeWidth="6"
            strokeLinecap="round"
          />
        </svg>
      </div>

      {/* Curva decorativa sutil no topo superior direito */}
      <div className="absolute -top-24 -right-24 w-96 h-96 pointer-events-none opacity-40">
        <svg viewBox="0 0 400 400" fill="none">
          <circle
            cx="200"
            cy="200"
            r="180"
            stroke="#F18800"
            strokeWidth="2.5"
            strokeDasharray="6 6"
          />
        </svg>
      </div>

      <div className="relative w-full max-w-md z-10 animate-fade-in-up my-6">
        {/* LOGO OFICIAL GRUPO ABR BRANCA COM TAGLINE INSTITUCIONAL */}
        <div className="flex flex-col items-center mb-6 text-center">
          <div className="mb-3 px-4 py-2">
            <AbrLogo variant="white" className="h-14 md:h-16 w-auto drop-shadow-sm" />
          </div>
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-white/10 text-white text-[11px] font-semibold tracking-wide border border-white/15">
            <Sparkles className="w-3.5 h-3.5 text-[#F18800]" />
            <span>ABR Intelligence · Plataforma Estratégica</span>
          </div>
          <p className="text-xs uppercase tracking-widest text-white/80 mt-2 font-medium">
            Comprar melhor. Vender melhor. Antecipar melhor.
          </p>
        </div>

        {/* CARD BRANCO ESTRUTURADO PARA O FORMULÁRIO */}
        <Card className="border-0 bg-white text-[#141D40] shadow-2xl rounded-2xl overflow-hidden relative">
          {/* Tarja / Linha superior Laranja ABR (#F18800) */}
          <div className="h-1.5 w-full bg-[#F18800]" />

          <CardHeader className="pb-3 pt-6 px-6">
            <div className="flex items-center justify-between">
              <CardTitle className="text-lg font-extrabold text-[#253575] tracking-tight">
                Acesso ao Sistema
              </CardTitle>
              <span className="text-[11px] font-bold text-[#F18800] uppercase tracking-wider">
                Seu Parceiraço!
              </span>
            </div>
            <CardDescription className="text-xs text-[#5C6784] mt-1">
              Insira suas credenciais corporativas do Grupo ABR
            </CardDescription>
          </CardHeader>

          <CardContent className="px-6 pb-6">
            <form onSubmit={handleSubmit} className="space-y-4">
              {errorMsg && (
                <div className="p-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-xs flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 shrink-0 text-red-600" />
                  <span>{errorMsg}</span>
                </div>
              )}

              <div className="space-y-1.5 text-left">
                <Label htmlFor="email" className="text-xs font-semibold text-[#253575]">
                  E-mail Corporativo
                </Label>
                <Input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="seu.nome@grupoabr.com.br"
                  required
                  className="bg-[#F4F6FB] border-[#D9DFEB] text-[#141D40] placeholder:text-[#8C98AC] focus-visible:ring-[#F18800] focus-visible:border-[#F18800] h-10 text-xs font-medium"
                />
              </div>

              <div className="space-y-1.5 text-left">
                <div className="flex items-center justify-between">
                  <Label htmlFor="password" className="text-xs font-semibold text-[#253575]">
                    Senha
                  </Label>
                  <span className="text-[11px] text-[#5C6784] cursor-not-allowed">
                    Esqueceu? Contate o TI
                  </span>
                </div>
                <Input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  required
                  className="bg-[#F4F6FB] border-[#D9DFEB] text-[#141D40] placeholder:text-[#8C98AC] focus-visible:ring-[#F18800] focus-visible:border-[#F18800] h-10 text-xs font-medium"
                />
              </div>

              {/* Botão de Ação Oficial em Laranja ABR #F18800 ("O laranja conduz") */}
              <Button
                type="submit"
                disabled={loading}
                className="w-full h-11 bg-[#F18800] hover:bg-[#D97900] active:bg-[#C26B00] text-white font-bold tracking-tight shadow-md transition-all flex items-center justify-center gap-2 mt-2 rounded-lg cursor-pointer"
              >
                {loading ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin text-white" />
                    <span>Autenticando...</span>
                  </>
                ) : (
                  <>
                    <span>Entrar no Cockpit</span>
                    <ArrowRight className="w-4 h-4" />
                  </>
                )}
              </Button>
            </form>

            {/* Acesso rápido para homologação / perfis demonstrativos */}
            <div className="mt-5 pt-4 border-t border-[#E8ECF4]">
              <div className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-[#253575] mb-2">
                <ShieldCheck className="w-3.5 h-3.5 text-[#F18800]" />
                <span>Acesso Rápido por Perfil</span>
              </div>
              <div className="grid grid-cols-1 gap-1.5">
                <button
                  type="button"
                  onClick={() => setDemoUser('pietra.leite@grupoabr.com.br')}
                  className="text-left px-2.5 py-1.5 rounded-md bg-[#F4F6FB] hover:bg-[#EAEFF9] border border-[#D9DFEB] text-xs text-[#141D40] flex items-center justify-between transition-colors cursor-pointer"
                >
                  <span className="font-semibold">Pietra Leite</span>
                  <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-[#253575] text-white">
                    Analista (Inteligência)
                  </span>
                </button>
                <button
                  type="button"
                  onClick={() => setDemoUser('thiago.almeida@grupoabr.com.br')}
                  className="text-left px-2.5 py-1.5 rounded-md bg-[#F4F6FB] hover:bg-[#EAEFF9] border border-[#D9DFEB] text-xs text-[#141D40] flex items-center justify-between transition-colors cursor-pointer"
                >
                  <span className="font-semibold">Thiago Almeida</span>
                  <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-[#253575] text-white">
                    Analista (Inteligência)
                  </span>
                </button>
                <button
                  type="button"
                  onClick={() => setDemoUser('marcelo.silva@grupoabr.com.br')}
                  className="text-left px-2.5 py-1.5 rounded-md bg-[#F4F6FB] hover:bg-[#EAEFF9] border border-[#D9DFEB] text-xs text-[#141D40] flex items-center justify-between transition-colors cursor-pointer"
                >
                  <span className="font-semibold">Marcelo Silva</span>
                  <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-[#142758] text-white">
                    Gerente Comercial
                  </span>
                </button>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Rodapé institucional com slogan do manual */}
        <div className="mt-5 text-center space-y-1 text-white/70">
          <div className="flex items-center justify-center gap-1.5 text-xs">
            <Lock className="w-3.5 h-3.5 text-[#F18800]" />
            <span>Ambiente Corporativo Seguro · Grupo ABR</span>
          </div>
          <p className="text-[10px] uppercase tracking-wider font-semibold text-white/60">
            Força para construir. Agilidade para entregar. Parceria para crescer.
          </p>
        </div>
      </div>
    </div>
  )
}
