"""Dicionário da categoria automática: termos comuns no Brasil (sem acento, minúsculas).

Cada termo casa com uma palavra da descrição (ou com o início dela, a partir de 4 letras:
"pizza" casa com "pizzaria"; "farmac" com "farmacia"). Termos com espaço casam como frase.
O termo mais longo vence quando mais de uma categoria aparece.
"""

WORDS: dict[str, str] = {}


def _add(category: str, text: str) -> None:
    for term in text.split(","):
        term = term.strip()
        if term:
            WORDS[term] = category


# ---------------------------------------------------------------- Alimentação
_add(
    "Alimentação",
    """
mercado, supermercado, hipermercado, minimercado, mercearia, emporio, quitanda, sacolao, hortifruti, hortifrutti,
feira, feirao, atacado, atacadao, atacadista, assai, carrefour, pao de acucar, extra mercado, mercado extra, big bompreco,
bompreco, sams club, makro, tenda atacado, fort atacadista, roldao, spani, max atacadista, mateus, supermercados bh, epa,
verdemar, condor, angeloni, savegnago, zaffari, bistek, giassi, comper, nordestao, guanabara, prezunic, mundial, zona sul,
st marche, oba hortifruti, dia supermercado, minuto pao de acucar, oxxo, daki, padaria, panificadora, confeitaria,
doceria, docaria, boleria, acougue, casa de carnes, frigorifico, peixaria, laticinio, adega, distribuidora de bebidas,
restaurante, lanchonete, lanche, lancheria, pastelaria, pastel, pizzaria, pizza, hamburgueria, hamburguer, burger,
sanduiche, sanduba, cachorro quente, hot dog, churrascaria, churrasco, rodizio, espetinho, buffet, self service,
marmita, marmitex, quentinha, prato feito, almoco, jantar, janta, cafe da manha, lanche da tarde, refeicao, comida,
delivery, ifood, ifd, rappi, aiqfome, uber eats, ze delivery, james delivery, goomer, anota ai, mcdonalds, mc donalds,
mcdonald, burger king, bk, habibs, giraffas, subway, kfc, popeyes, outback, madero, coco bambu, spoleto, china in box,
bobs, starbucks, cacau show, kopenhagen, chocolates brasil cacau, dominos, pizza hut, jeronimo, divino fogao, ragazzo,
viena, frango assado, fogo de chao, sorveteria, sorvete, gelato, acai, acaiteria, cafe, cafeteria, cafezinho,
padoca, bar e lanchonete, salgado, salgadinho, coxinha, esfiha, esfirra, empada, tapioca, crepe, sushi, temaki,
japones, comida japonesa, comida chinesa, yakisoba, poke, churros, pipoca, doce, doces, bolo, torta, brigadeiro,
chocolate, bombom, biscoito, bolacha, salgadinhos, chips, cereal, granola, aveia, arroz, feijao, macarrao, massa,
farinha, acucar, sal, oleo, azeite, vinagre, molho, tempero, cafe em po, leite, iogurte, queijo, manteiga, margarina,
requeijao, creme de leite, leite condensado, ovo, ovos, pao, paes, frios, presunto, mortadela, salame, peito de peru,
carne, picanha, alcatra, contra file, patinho, acem, costela, frango, peito de frango, coxa, linguica, salsicha,
bacon, peixe, tilapia, salmao, camarao, atum, sardinha, fruta, frutas, banana, maca, laranja, limao, mamao, melancia,
uva, morango, abacaxi, manga, verdura, verduras, legume, legumes, alface, tomate, cebola, alho, batata, cenoura,
mandioca, aipim, macaxeira, brocolis, abobora, chuchu, pepino, pimentao, agua mineral, agua de coco, refrigerante,
coca cola, guarana, suco, cha, energetico, isotonico, cerveja, chopp, chope, vinho, cachaca, vodka, whisky, gin,
destilado, bebida, bebidas, gelo, carvao, congelado, congelados, lasanha, sorvete de massa, petisco, porcao,
food truck, quiosque, cantina, refeitorio, vale refeicao, alimentacao, rancho, compras do mes, comprinhas do mes
""",
)

# ---------------------------------------------------------------- Transporte
_add(
    "Transporte",
    """
uber, uber trip, 99, 99app, 99 pop, 99taxi, cabify, indriver, in driver, buser, blablacar, taxi, mototaxi, moto taxi,
onibus, metro, metro sp, trem, cptm, supervia, brt, vlt, bilhete unico, bilhete, passagem de onibus, passe de onibus,
passe, vale transporte, recarga top, cartao top, bom, riocard, sptrans, bhbus, move metropolitano, cartao bem,
cartao transporte, transporte publico, rodoviaria, passagem rodoviaria, clickbus, guichevirtual, combustivel,
gasolina, gasolina aditivada, etanol, alcool combustivel, diesel, gnv, abastecimento, abastecer, posto, auto posto,
posto de gasolina, shell, ipiranga, br distribuidora, petrobras posto, ale combustiveis, raizen, vibra, sem parar,
conectcar, veloe, move mais, taggy, pedagio, estacionamento, estapar, zona azul, parking, parquimetro, valet,
lava rapido, lava jato, lavagem do carro, ducha, polimento, oficina, mecanico, mecanica, auto center, autocenter,
funilaria, pintura automotiva, borracharia, pneu, pneus, alinhamento, balanceamento, troca de oleo, oleo do motor,
filtro de oleo, revisao, revisao do carro, bateria do carro, autopecas, auto pecas, pecas, embreagem, freio, pastilha,
ipva, licenciamento, dpvat, detran, multa de transito, multa, cnh, autoescola, auto escola, seguro auto, seguro do carro,
seguro da moto, porto seguro auto, financiamento do carro, parcela do carro, consorcio do carro, aluguel de carro,
locadora, localiza, movida, unidas, rent a car, carro por assinatura, bicicleta, bike, patinete, yellow, tembici,
bike itau, pedal, capacete, motoboy, frete, mudanca transporte, despachante, vistoria, guincho, reboque
""",
)

# ---------------------------------------------------------------- Moradia
_add(
    "Moradia",
    """
aluguel, condominio, condominio predial, taxa condominial, iptu, financiamento imobiliario, financiamento da casa,
prestacao da casa, prestacao do apartamento, caixa habitacao, consorcio imovel, luz, energia, energia eletrica,
conta de luz, enel, cemig, copel, light, coelba, celpe, cosern, energisa, equatorial, cpfl, eletropaulo, elektro,
celesc, rge, ceee, neoenergia, amazonas energia, agua, conta de agua, saneamento, sabesp, copasa, cedae, aguas rio,
embasa, compesa, sanepar, corsan, casan, cagece, caesb, gas, gas encanado, comgas, naturgy, gas de cozinha, botijao,
ultragaz, liquigas, supergasbras, nacional gas, copagaz, reforma, obra, material de construcao, leroy merlin,
telhanorte, c&c, cec, casa show, tumelero, madeireira, ferragem, ferragista, ferramenta, pedreiro, eletricista,
encanador, pintor, marceneiro, vidraceiro, serralheiro, chaveiro, dedetizacao, desentupidora, diarista, faxina,
faxineira, empregada domestica, domestica, passadeira, jardineiro, jardinagem, piscineiro, moveis, movel, sofa,
colchao, cama, guarda roupa, armario, mesa, cadeira, tok stok, etna, mobly, madeiramadeira, casas bahia moveis,
eletrodomestico, geladeira, fogao, maquina de lavar, lava loucas, microondas, ar condicionado, ventilador, chuveiro,
cortina, tapete, decoracao, utensilios, panela, roupa de cama, toalha, limpeza, produtos de limpeza, detergente,
sabao em po, amaciante, desinfetante, agua sanitaria, vassoura, seguro residencial, seguro da casa, iptu parcela,
mudanca, caminhao de mudanca, portaria, interfone, chave, fechadura, lampada, manutencao da casa
""",
)

# ---------------------------------------------------------------- Saúde
_add(
    "Saúde",
    """
farmacia, drogaria, drogasil, droga raia, raia, pague menos, panvel, drogarias pacheco, pacheco, sao joao farmacia,
farmacias sao joao, drogaria sao paulo, venancio, nissei, extrafarma, ultrafarma, farmacia popular, onofre,
remedio, remedios, medicamento, medicamentos, receita medica, vitamina, suplemento, whey, creatina, consulta,
consulta medica, medico, medica, clinica, clinica medica, hospital, pronto socorro, upa, laboratorio, exame, exames,
hemograma, ultrassom, raio x, ressonancia, tomografia, dentista, odonto, odontologia, ortodontista, aparelho dental,
canal dentario, limpeza dental, psicologo, psicologa, psicoterapia, terapia, terapeuta, psiquiatra, fisioterapia,
fisioterapeuta, fono, fonoaudiologa, nutricionista, nutri, dermatologista, ginecologista, pediatra, oftalmologista,
cardiologista, ortopedista, otica, oticas carol, oculos, lente de contato, plano de saude, convenio medico,
unimed, amil, hapvida, notredame, intermedica, sulamerica saude, bradesco saude, porto saude, prevent senior, golden
cross, cassi, geap, odontoprev, seguro saude, vacina, vacinacao, curativo, termometro, academia, smart fit, smartfit,
bluefit, bodytech, selfit, crossfit, pilates, yoga, personal trainer, natacao, gympass, wellhub, totalpass, massagem,
quiropraxia, acupuntura, podologo, podologia, cirurgia, internacao, ambulancia, cuidador, home care
""",
)

# ---------------------------------------------------------------- Educação
_add(
    "Educação",
    """
escola, colegio, faculdade, universidade, mensalidade escolar, mensalidade da faculdade, matricula, rematricula,
creche, berçario, bercario, educacao infantil, curso, cursos, curso online, curso de ingles, ingles, idiomas,
espanhol, wizard, ccaa, fisk, cna, cultura inglesa, open english, duolingo plus, udemy, alura, coursera, hotmart,
domestika, descomplica, estrategia concursos, gran cursos, cursinho, pre vestibular, vestibular, enem, concurso,
inscricao concurso, livro, livros, livraria, saraiva, amazon livros, leitura cultura, apostila, material escolar,
caderno, lapis, caneta, mochila escolar, uniforme escolar, uniforme, pos graduacao, pos, mba, mestrado, doutorado,
especializacao, aula particular, professor particular, reforco escolar, transporte escolar, van escolar, perua escolar,
fies, prouni, taxa de diploma, xerox, copias, impressao, grafica, workshop, palestra, congresso, certificacao
""",
)

# ---------------------------------------------------------------- Serviços (casa, telefone, banco, pessoais)
_add(
    "Serviços",
    """
internet, banda larga, fibra, wifi, telefone, telefonia, celular, plano de celular, conta de celular, recarga celular,
recarga, vivo, claro, tim, oi, algar, nextel, net claro, sky, tv a cabo, tv por assinatura, brisanet, desktop internet,
tarifa, tarifa bancaria, cesta de servicos, anuidade, anuidade do cartao, taxa bancaria, iof, juros, juros do cartao,
encargos, ted, doc, saque, banco, cartorio, reconhecimento de firma, autenticacao, segunda via, correios, sedex,
envio, contador, contabilidade, advogado, advocacia, honorarios, despachante documentos, lavanderia, lavanderia omo,
tinturaria, costureira, conserto de roupa, sapateiro, conserto, assistencia tecnica, conserto de celular,
cabeleireiro, cabelereiro, salao, salao de beleza, barbearia, barbeiro, manicure, pedicure, unha, depilacao,
sobrancelha, estetica, esteticista, maquiagem, cosmeticos, perfumaria, perfume, boticario, o boticario, natura,
avon, eudora, sephora, quem disse berenice, shampoo, condicionador, sabonete, desodorante, creme dental, pasta de dente,
escova de dente, fio dental, absorvente, fralda, fraldas, papel higienico, higiene, higiene pessoal, seguro de vida,
seguro celular, previdencia privada, taxa, servico, servicos, impressora, cartucho, toner, chip
""",
)

# ---------------------------------------------------------------- Assinaturas (streaming, apps, nuvem)
_add(
    "Assinaturas",
    """
assinatura, assinaturas, mensalidade app, netflix, spotify, deezer, tidal, apple music, youtube premium, youtube music,
amazon prime, prime video, disney, disney plus, star plus, max, hbo, hbo max, globoplay, paramount, paramount plus,
apple tv, crunchyroll, mubi, telecine, premiere, sportv, dazn, nba league pass, twitch, patreon, onlyfans, kindle
unlimited, audible, skeelo, ubook, storytel, icloud, google one, google storage, dropbox, onedrive, microsoft 365,
office 365, adobe, creative cloud, canva, notion, chatgpt, openai, claude, anthropic, github, figma, linkedin premium,
tinder, bumble, happn, xbox game pass, game pass, playstation plus, ps plus, nintendo online, ea play, apple one,
apple com bill, google play, app store, assinatura revista, jornal, folha de sp, estadao, o globo digital,
clube do vinho, wine, tag livros, clube de assinatura, nubank ultravioleta, mensalidade clube
""",
)

# ---------------------------------------------------------------- Lazer
_add(
    "Lazer",
    """
cinema, cinemark, cinepolis, kinoplex, uci, ingresso, ingressos, ingresso com, sympla, eventim, ticketmaster, show,
shows, festival, teatro, museu, exposicao, parque, parque de diversoes, beto carrero, hopi hari, zoologico, aquario,
viagem, viagens, hotel, pousada, hostel, airbnb, booking, decolar, 123 milhas, 123milhas, hurb, cvc, passagem aerea,
passagem de aviao, latam, gol, azul linhas, aeroporto, bagagem, resort, cruzeiro, turismo, passeio, excursao,
bar, boteco, barzinho, pub, balada, festa, aniversario, presente, presentes, lembrancinha, churrasco com amigos,
happy hour, karaoke, boliche, sinuca, kart, paintball, escape room, jogo, jogos, game, games, steam, epic games,
playstation, xbox, nintendo, videogame, brinquedo, brinquedos, ri happy, pbkids, hobby, artesanato, fotografia,
instrumento musical, violao, praia, clube, camping, pescaria, esporte, futebol, pelada, quadra, ingresso de jogo,
socio torcedor, aposta, loteria, mega sena, lotofacil, bet, cassino, tabacaria, narguile, cigarro, charuto, revista
""",
)

# ---------------------------------------------------------------- Compras (roupas, eletrônicos, lojas)
_add(
    "Compras",
    """
roupa, roupas, vestuario, calcado, calcados, sapato, tenis, sandalia, chinelo, bolsa, mochila, carteira de couro,
cinto, camisa, camiseta, calca, bermuda, vestido, saia, jaqueta, casaco, moletom, blusa, lingerie, cueca, meia,
pijama, acessorios, bijuteria, joia, joalheria, relogio, oculos de sol, renner, riachuelo, c&a, cea, marisa, hering,
zara, shein, shopee, aliexpress, temu, mercado livre, mercadolivre, mercadopago compra, amazon, amazon br, magalu,
magazine luiza, americanas, casas bahia, ponto frio, extra com, kabum, fast shop, submarino, netshoes, centauro,
decathlon, dafiti, nike, adidas, puma, olympikus, havaianas, arezzo, schutz, melissa, vivara, pandora, polishop,
eletronico, eletronicos, celular novo, smartphone, iphone, samsung galaxy, notebook, computador, tablet, ipad,
fone de ouvido, fone, headset, carregador, cabo usb, televisao, tv, smart tv, console, monitor, teclado, mouse,
camera, caixa de som, alexa, echo dot, smartwatch, apple watch, presente online, loja, lojas, shopping, magazine,
departamento, outlet, brecho, enjoei
""",
)

# ---------------------------------------------------------------- Pets
_add(
    "Pets",
    """
pet, pets, pet shop, petshop, petz, cobasi, petlove, pet love, racao, racao gato, racao cachorro, areia de gato,
areia higienica, petisco pet, veterinario, veterinaria, clinica veterinaria, vet, vacina pet, vacina do cachorro,
vacina do gato, castracao, banho e tosa, tosa, adestrador, adestramento, hotel pet, creche pet, dog walker,
passeador, antipulgas, vermifugo, coleira, caminha pet, brinquedo pet, aquario peixe, ave, passaro
""",
)

# Termos muito curtos ou ambíguos que só valem como palavra inteira (nunca como começo de outra).
EXACT_ONLY = {
    "99",
    "bk",
    "oi",
    "tim",
    "bar",
    "pet",
    "vet",
    "gas",
    "max",
    "bet",
    "tv",
    "pao",
    "sal",
    "cha",
    "ovo",
    "pos",
    "bom",
    "epa",
    "uci",
    "gol",
    "azul",
    "luz",
    "agua",
    "pedal",
    "fone",
    "chip",
    "taxa",
    "unha",
}

# Categoria que recebe o termo quando o usuário não tem a categoria padrão.
FALLBACK = {"Assinaturas": "Serviços", "Compras": "Outros", "Pets": "Outros"}
