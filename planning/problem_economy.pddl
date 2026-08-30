(define (problem sc2-economy)
  (:domain sc2-terran-macro)
  (:init
    (= (minerals) 50)
    (= (vespene) 0)
    (= (supply-used) 12)
    (= (supply-cap) 15)
    (= (barracks-count) 0)
    (= (marine-count) 0)
    (= (depot-count) 0) ;
  )
  (:goal (and
    (>= (barracks-count) 3)
    (>= (marine-count) 15)
  ))
)