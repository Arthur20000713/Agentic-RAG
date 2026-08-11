package com.livestock.platform.livestock.service;

import com.livestock.platform.ai.AiMeasurementRequest;
import com.livestock.platform.ai.AiMeasurementResponse;
import com.livestock.platform.ai.MeasurementClientException;
import com.livestock.platform.ai.PythonAiMeasurementClient;
import com.livestock.platform.audit.AuditEvent;
import com.livestock.platform.audit.AuditRequestMetadata;
import com.livestock.platform.audit.AuditService;
import com.livestock.platform.common.error.ApiException;
import com.livestock.platform.common.web.RequestIds;
import com.livestock.platform.livestock.api.BodyMeasurementValues;
import com.livestock.platform.livestock.api.MeasurementAnalyzeRequest;
import com.livestock.platform.livestock.api.MeasurementAnalyzeResponse;
import com.livestock.platform.security.UserPrincipal;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HashMap;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Service;

@Service
public class MeasurementAnalysisService {

    private final LivestockSnapshotService snapshotService;
    private final PythonAiMeasurementClient aiClient;
    private final AuditService auditService;

    public MeasurementAnalysisService(
            LivestockSnapshotService snapshotService,
            PythonAiMeasurementClient aiClient,
            AuditService auditService
    ) {
        this.snapshotService = snapshotService;
        this.aiClient = aiClient;
        this.auditService = auditService;
    }

    public MeasurementAnalyzeResponse analyze(
            MeasurementAnalyzeRequest payload,
            String idempotencyKey,
            UserPrincipal actor,
            AuditRequestMetadata metadata
    ) {
        AuthorizedMeasurementSnapshot snapshot = snapshotService.load(
                payload.animalId(),
                actor
        );
        String digest = deterministicDigest(actor.userId(), idempotencyKey);
        String internalRequestId = "req_measure_" + digest;
        String operationId = "op_measure_" + digest;
        AiMeasurementRequest aiRequest = toAiRequest(
                payload,
                snapshot,
                actor.userId(),
                internalRequestId,
                operationId
        );
        AiMeasurementResponse aiResponse;
        try {
            aiResponse = aiClient.analyze(aiRequest);
        } catch (MeasurementClientException exception) {
            throw new ApiException(
                    exception.status(),
                    exception.code(),
                    exception.getMessage()
            );
        }

        auditService.append(new AuditEvent(
                Long.valueOf(actor.userId()),
                "MEASUREMENT_ANALYZED",
                "ANIMAL",
                String.valueOf(snapshot.animalId()),
                RequestIds.current(),
                "SUCCESS",
                metadata.clientIp(),
                metadata.userAgent(),
                Map.of(
                        "internalRequestId", internalRequestId,
                        "operationId", operationId,
                        "outcome", aiResponse.outcome().name(),
                        "historyCount", snapshot.history().size()
                )
        ));
        return toPublicResponse(operationId, snapshot, aiResponse);
    }

    private static AiMeasurementRequest toAiRequest(
            MeasurementAnalyzeRequest payload,
            AuthorizedMeasurementSnapshot snapshot,
            String userId,
            String requestId,
            String operationId
    ) {
        Map<String, Object> attributes = new HashMap<>();
        attributes.put("databaseId", snapshot.animalId());
        if (snapshot.farmId() != null) {
            attributes.put("farmId", snapshot.farmId());
        }
        return new AiMeasurementRequest(
                requestId,
                operationId,
                userId,
                new AiMeasurementRequest.AnimalSnapshot(
                        snapshot.animalCode(),
                        snapshot.species(),
                        snapshot.breed(),
                        snapshot.sex(),
                        snapshot.birthDate(),
                        attributes
                ),
                snapshot.ageMonth(),
                toAiValues(payload.current()),
                snapshot.history().stream()
                        .map(item -> new AiMeasurementRequest.HistoryItem(
                                item.measureDate(),
                                item.bodyHeightCm(),
                                item.bodyLengthCm(),
                                item.chestGirthCm(),
                                item.chestDepthCm(),
                                item.chestWidthCm(),
                                item.weightKg()
                        ))
                        .toList(),
                payload.confidence(),
                false,
                10000
        );
    }

    private static AiMeasurementRequest.Values toAiValues(BodyMeasurementValues values) {
        return new AiMeasurementRequest.Values(
                values.bodyHeightCm(),
                values.bodyLengthCm(),
                values.chestGirthCm(),
                values.chestDepthCm(),
                values.chestWidthCm(),
                values.weightKg()
        );
    }

    private static MeasurementAnalyzeResponse toPublicResponse(
            String operationId,
            AuthorizedMeasurementSnapshot snapshot,
            AiMeasurementResponse response
    ) {
        AiMeasurementResponse.Analysis result = response.result();
        return new MeasurementAnalyzeResponse(
                operationId,
                MeasurementAnalyzeResponse.Outcome.valueOf(response.outcome().name()),
                snapshot.animalId(),
                snapshot.animalCode(),
                new MeasurementAnalyzeResponse.Analysis(
                        result.summary(),
                        result.abnormalItems(),
                        result.evidence(),
                        result.recommendation(),
                        result.report(),
                        result.usedDemoHistory()
                )
        );
    }

    private static String deterministicDigest(String userId, String idempotencyKey) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            return HexFormat.of().formatHex(
                    digest.digest(
                            (userId + '\0' + idempotencyKey)
                                    .getBytes(StandardCharsets.UTF_8)
                    )
            );
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 is unavailable", exception);
        }
    }
}
