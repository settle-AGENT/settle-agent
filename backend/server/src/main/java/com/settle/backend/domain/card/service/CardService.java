package com.settle.backend.domain.card.service;

import com.settle.backend.common.exception.DuplicateResourceException;
import com.settle.backend.common.exception.ResourceNotFoundException;
import com.settle.backend.domain.card.dto.RegisterCardCommand;
import com.settle.backend.domain.card.entity.Card;
import com.settle.backend.domain.card.repository.CardRepository;
import com.settle.backend.domain.member.repository.MemberRepository;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional(readOnly = true)
public class CardService {

    private final CardRepository cardRepository;
    private final MemberRepository memberRepository;

    public CardService(CardRepository cardRepository, MemberRepository memberRepository) {
        this.cardRepository = cardRepository;
        this.memberRepository = memberRepository;
    }

    @Transactional
    public Card register(UUID memberId, RegisterCardCommand command) {
        var member = memberRepository.findById(memberId)
                .orElseThrow(() -> new ResourceNotFoundException("사용자를 찾을 수 없습니다: " + memberId));
        if (cardRepository.existsByMember_Id(memberId)) {
            throw new DuplicateResourceException("이미 등록된 카드가 있습니다: " + memberId);
        }
        if (command.stayEndDate().isBefore(command.stayStartDate())) {
            throw new IllegalArgumentException("체류 종료일은 시작일보다 빠를 수 없습니다.");
        }

        return cardRepository.save(new Card(
                member,
                command.name(),
                command.stayQualification(),
                command.registrationNumberEncrypted(),
                command.stayAddress(),
                command.stayStartDate(),
                command.stayEndDate(),
                command.passportNumberEncrypted(),
                command.passportExpiresOn(),
                command.registrationFrontImageUrl(),
                command.registrationBackImageUrl(),
                command.passportImageUrl(),
                command.accountPurposes()
        ));
    }

    public Card getByMemberId(UUID memberId) {
        return cardRepository.findByMember_Id(memberId)
                .orElseThrow(() -> new ResourceNotFoundException("등록된 카드를 찾을 수 없습니다: " + memberId));
    }
}
