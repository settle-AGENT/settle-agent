package com.settle.backend.domain.document.repository;

import static org.assertj.core.api.Assertions.assertThat;

import com.settle.backend.domain.document.entity.GeneratedDocument;
import com.settle.backend.domain.document.entity.GeneratedDocumentStatus;
import com.settle.backend.domain.member.entity.Member;
import com.settle.backend.domain.member.repository.MemberRepository;
import jakarta.persistence.EntityManager;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

@DataJpaTest
class GeneratedDocumentRepositoryTest {

    @Autowired
    private GeneratedDocumentRepository generatedDocumentRepository;

    @Autowired
    private MemberRepository memberRepository;

    @Autowired
    private EntityManager entityManager;

    @Test
    void savesMetadataAndFindsReadyDocumentOwnedByMember() {
        Member member = memberRepository.save(new Member("document@example.com", "password-hash"));
        GeneratedDocument document = new GeneratedDocument(
                UUID.fromString("20000000-0000-0000-0000-000000000001"),
                member,
                "demo-001",
                "open_bank_account",
                "계좌개설신청서",
                "members/%s/generated-documents/document-1.pdf".formatted(member.getId())
        );
        document.markReady(List.of("영문 이름을 확인해 주세요."));
        GeneratedDocument saved = generatedDocumentRepository.saveAndFlush(document);

        entityManager.clear();

        GeneratedDocument found = generatedDocumentRepository
                .findByIdAndMember_Id(saved.getId(), member.getId())
                .orElseThrow();
        assertThat(found.getStatus()).isEqualTo(GeneratedDocumentStatus.READY);
        assertThat(found.getWarnings()).containsExactly("영문 이름을 확인해 주세요.");

    }

    @Test
    void doesNotReturnDocumentToAnotherMember() {
        Member owner = memberRepository.save(new Member("owner@example.com", "password-hash"));
        Member other = memberRepository.save(new Member("other@example.com", "password-hash"));
        GeneratedDocument saved = generatedDocumentRepository.saveAndFlush(new GeneratedDocument(
                UUID.fromString("20000000-0000-0000-0000-000000000002"),
                owner,
                "demo-001",
                "open_bank_account",
                "계좌개설신청서",
                "members/%s/generated-documents/document-2.pdf".formatted(owner.getId())
        ));

        assertThat(generatedDocumentRepository.findByIdAndMember_Id(saved.getId(), other.getId()))
                .isEmpty();
    }
}
