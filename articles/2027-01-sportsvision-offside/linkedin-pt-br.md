<!-- Post LinkedIn (PT-BR), ~1.400 caracteres. -->

Cinco correções certas, nenhum impedimento marcado.

Montei um pipeline que recebe vídeo de futebol e deveria devolver, para cada passe, uma decisão de impedimento com a geometria. Go nas regras, Python na visão, filas e autoscaling num cluster Kubernetes local. Durante quatro semanas, com vídeo real, ele não chegou a nenhum veredito.

O que encontrei:

→ Decidir é barato, enxergar é caro: no benchmark, as regras levaram 0,023 s e a percepção 100,2 s no mesmo vídeo de 10 s.

→ Um modelo dedicado levou a visibilidade da bola de 47% para 93%. Zero eventos: a trajetória chegava a 666 km/h. O detector errava com confiança.

→ Um filtro de movimento reduziu o pior salto da bola de 12,14 m para 1,63 m. Primeiro evento: "inconclusivo".

→ O detector treinado ficou quase duas semanas no disco enquanto o cluster rodava o antigo.

→ O último bloqueio estava na camada barata e determinística: a posse exigia 3 quadros consecutivos, e o cluster só olha um a cada dois. 0 de 599 quadros, com qualquer raio de posse.

Depois dessa correção: os dois primeiros vereditos, ambos "posição legal". Não tenho trechos rotulados, então não sei se estão certos, e eles vêm de rodar as regras sobre artefatos salvos, não de uma execução completa no cluster. Não existe número de acurácia.

A lição: uma execução que não emite nada precisa dizer por quê.

Texto completo e projeto: [[LINK]]

#VisãoComputacional #MLOps #Kubernetes #Golang #Python #EngenhariaDeSoftware
