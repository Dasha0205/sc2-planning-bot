(define (problem sc2-classical)
    (:domain sc2-terran-classical)

    (:objects
        depot1 depot2 depot3 depot4 depot5 depot6 - depot
        barracks1 barracks2 barracks3 barracks4 - barracks
        refinery1 refinery2 - refinery
        factory1 - factory
        ebay1 - ebay
        cc1 cc2 cc3 - cc
        s1 s2 s3 s4 s5 s6 s7 s8 s9 s10 s11 s12 s13 s14 s15 s16 s17 s18 s19 s20 s21 s22 s23 s24 s25 - slot
        marine1 marine2 marine3 marine4 marine5 marine6 - marine
    )

    (:init
        (built cc1)
        (free s1)
        (unlocks depot1 s2)
        (unlocks depot1 s3)
        (unlocks depot1 s4)
        (unlocks depot1 s5)
        (unlocks depot2 s6)
        (unlocks depot2 s7)
        (unlocks depot2 s8)
        (unlocks depot2 s9)
        (unlocks depot3 s10)
        (unlocks depot3 s11)
        (unlocks depot3 s12)
        (unlocks depot3 s13)
        (unlocks depot4 s14)
        (unlocks depot4 s15)
        (unlocks depot4 s16)
        (unlocks depot4 s17)
        (unlocks depot5 s18)
        (unlocks depot5 s19)
        (unlocks depot5 s20)
        (unlocks depot5 s21)
        (unlocks depot6 s22)
        (unlocks depot6 s23)
        (unlocks depot6 s24)
        (unlocks depot6 s25)
    )

    (:goal (and
        (built barracks1)
        (trained marine1)
        (trained marine2)
        (trained marine3)
        (trained marine4)
        (trained marine5)
        (trained marine6)
    ))
)
