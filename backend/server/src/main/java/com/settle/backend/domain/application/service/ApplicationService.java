package com.settle.backend.domain.application.service;

import com.settle.backend.common.exception.ResourceNotFoundException;
import com.settle.backend.domain.application.entity.AccountOpeningApplication;
import com.settle.backend.domain.application.entity.IntegratedApplication;
import com.settle.backend.domain.application.repository.AccountOpeningApplicationRepository;
import com.settle.backend.domain.application.repository.IntegratedApplicationRepository;
import com.settle.backend.domain.member.entity.Member;
import com.settle.backend.domain.member.repository.MemberRepository;
import java.util.List;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional(readOnly = true)
public class ApplicationService {

    private final MemberRepository memberRepository;
    private final AccountOpeningApplicationRepository accountOpeningRepository;
    private final IntegratedApplicationRepository integratedRepository;

    public ApplicationService(
            MemberRepository memberRepository,
            AccountOpeningApplicationRepository accountOpeningRepository,
            IntegratedApplicationRepository integratedRepository
    ) {
        this.memberRepository = memberRepository;
        this.accountOpeningRepository = accountOpeningRepository;
        this.integratedRepository = integratedRepository;
    }

    @Transactional
    public AccountOpeningApplication createAccountOpening(UUID memberId, String s3Url) {
        return accountOpeningRepository.save(new AccountOpeningApplication(getMember(memberId), s3Url));
    }

    public List<AccountOpeningApplication> getAccountOpenings(UUID memberId) {
        getMember(memberId);
        return accountOpeningRepository.findAllByMember_IdOrderByCreatedAtDesc(memberId);
    }

    @Transactional
    public IntegratedApplication createIntegrated(UUID memberId, String s3Url) {
        return integratedRepository.save(new IntegratedApplication(getMember(memberId), s3Url));
    }

    public List<IntegratedApplication> getIntegratedApplications(UUID memberId) {
        getMember(memberId);
        return integratedRepository.findAllByMember_IdOrderByCreatedAtDesc(memberId);
    }

    private Member getMember(UUID memberId) {
        return memberRepository.findById(memberId)
                .orElseThrow(() -> new ResourceNotFoundException("사용자를 찾을 수 없습니다: " + memberId));
    }
}
