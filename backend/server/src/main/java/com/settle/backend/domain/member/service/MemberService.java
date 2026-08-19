package com.settle.backend.domain.member.service;

import com.settle.backend.common.exception.ResourceNotFoundException;
import com.settle.backend.domain.member.entity.Member;
import com.settle.backend.domain.member.repository.MemberRepository;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional(readOnly = true)
public class MemberService {

    private final MemberRepository memberRepository;

    public MemberService(MemberRepository memberRepository) {
        this.memberRepository = memberRepository;
    }

    public Member get(UUID memberId) {
        return memberRepository.findById(memberId)
                .orElseThrow(() -> new ResourceNotFoundException("사용자를 찾을 수 없습니다: " + memberId));
    }
}
